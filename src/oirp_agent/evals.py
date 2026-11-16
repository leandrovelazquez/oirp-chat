"""
The eval runner: runs evals/questions.yaml through the real agent and scores it.

    python -m oirp_agent.evals --check            free: validate the file, run every expected query
    python -m oirp_agent.evals                    every question (calls the model; prints cost)
    python -m oirp_agent.evals --only wh_suppression,wh_admissions_funnel
    python -m oirp_agent.evals --limit 5 --max-cost 1.00 --model claude-sonnet-5-5

How a question is scored (each check only when the question asks for it):

- **confidence**: the turn's tier is the expected one (or one of a list);
- **kpi / tool**: the expected KPI was looked up or searched, the expected tool called;
- **rows**: for `expected_tool_input`, some `query_metric` call the agent made
  returns the same rows as the expected query. Rows are compared, not query
  text, so a different but equivalent query passes;
- **facts**: every key fact appears in what the user sees, the answer text plus
  the number tables drawn from tool results;
- **reason**: for `expected_could_not_answer`, the "can't answer" reason is the
  expected one (`none` = it must answer), with at least one suggested question;
- **numbers**: always. No number in the text that no tool returned (numbers.py).

A question passes when all of its checks pass. The report gives the pass rate
for answerable questions and for refusals separately, against the bar below,
plus tool calls, rewrites, latency (p50/p95), tokens and an estimated cost.
Results go to evals/results/<timestamp>-<model>.json and a Markdown summary
beside it.

No test calls the model; this runner is the only thing that does, and only
when run on purpose.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .cannot_answer import REASONS

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "evals" / "questions.yaml"
RESULTS = ROOT / "evals" / "results"
SL = ROOT / "semantic_layer"

# The bar a run must clear, with a latency allowance for a ~60k-token prompt
# (5.x tokenizer) and multi-step tool use.
BAR_ANSWERABLE = 0.90
BAR_REFUSALS = 1.00
BAR_P95_SECONDS = 45.0

# USD per million tokens: input, output, cache write (5-minute), cache read.
# From the Claude API reference, 2026-11. Estimates: check current pricing.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00, 3.75, 0.30),
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),   # prompts up to 100K tokens; ours is ~60K
    "claude-opus-5": (5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5": (2.00, 10.00, 2.50, 0.20),
    "claude-opus-4-8": (5.00, 25.00, 6.25, 0.50),
}


def cost_usd(model: str, usage: dict[str, int]) -> float | None:
    p = PRICES.get(model)
    if p is None:
        return None
    return (usage.get("input_tokens", 0) * p[0] + usage.get("output_tokens", 0) * p[1]
            + usage.get("cache_creation_input_tokens", 0) * p[2]
            + usage.get("cache_read_input_tokens", 0) * p[3]) / 1e6


# ------------------------------------------------------------------ loading


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("evals") or [])


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _spec_query(engine, spec: dict) -> dict:
    return engine.query(spec["cube"], list(spec.get("measures") or []), by=spec.get("by"),
                        filters=spec.get("filters"))


def check_definitions(questions: list[dict], engine, store) -> list[str]:
    """Problems with the eval file itself. Free: no model call."""
    problems: list[str] = []
    ids: set[str] = set()
    kpis = {k["kpi_id"] for k in store.list_kpis()}
    for i, q in enumerate(questions):
        qid = q.get("id") or f"#{i}"
        if not q.get("id") or not q.get("question"):
            problems.append(f"{qid}: needs an id and a question")
        if qid in ids:
            problems.append(f"{qid}: duplicate id")
        ids.add(qid)
        if q.get("follow_up") and i == 0:
            problems.append(f"{qid}: follow_up on the first question")
        kpi = q.get("expected_kpi")
        if kpi not in (None, "any") and kpi not in kpis:
            problems.append(f"{qid}: expected_kpi {kpi!r} is not a KPI")
        for c in _as_list(q.get("expected_confidence")):
            if c not in ("high", "medium", "low", "none"):
                problems.append(f"{qid}: unknown confidence {c!r}")
        for r in _as_list(q.get("expected_could_not_answer")):
            if r != "none" and r not in REASONS:
                problems.append(f"{qid}: unknown could_not_answer reason {r!r}")
        spec = q.get("expected_tool_input")
        if spec:
            if engine is None:
                problems.append(f"{qid}: expected_tool_input but no warehouse loaded")
                continue
            try:
                r = _spec_query(engine, spec)
                if not r["rows"]:
                    problems.append(f"{qid}: expected query returns no rows")
            except Exception as e:  # QueryError, or a bad spec shape
                problems.append(f"{qid}: expected query fails: {e}")
    return problems


# ------------------------------------------------------------------ scoring


def _norm(s: str) -> str:
    """Lower case; underscores, dashes and hyphens as spaces ("as-of" = "as of");
    no markdown emphasis or double quotes; one apostrophe; single spaces."""
    s = s.lower().replace("_", " ")
    s = re.sub(r"[‐-―−-]", " ", s)
    s = re.sub(r"[*`\"“”]", "", s)
    s = s.replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def _visible_text(text: str, tables: list[dict]) -> str:
    parts = [text]
    for t in tables:
        parts += [t.get("title", ""), t.get("subtitle", ""), *t.get("notes", [])]
        parts += [c["name"] for c in t.get("columns", [])]
        parts += [cell for row in t.get("rows", []) for cell in row]
    return _norm("\n".join(str(p) for p in parts))


def _row_key(row: dict, by: list[str], measures: list[str]) -> tuple:
    return (tuple(str(row.get(b)) for b in by),
            tuple(None if row.get(m) is None else round(float(row[m]), 6) for m in measures))


def rows_match(engine, spec: dict, actual_inputs: list[dict]) -> tuple[bool, str]:
    """Does any of the agent's query_metric calls return the expected rows?"""
    expected = _spec_query(engine, spec)
    e_by = expected["by"]
    e_measures = [m["name"] for m in expected["measures"]]
    want = {_row_key(r, e_by, e_measures) for r in expected["rows"]}
    tried = 0
    for inp in actual_inputs:
        if str(inp.get("cube", "")).lower() != spec["cube"].lower():
            continue
        try:
            got = engine.query(inp.get("cube", ""), list(inp.get("measures") or []), by=inp.get("by"),
                               filters=inp.get("filters"))
        except Exception:
            continue
        tried += 1
        if len(got["by"]) != len(e_by):
            continue
        names = {m["name"].lower(): m["name"] for m in got["measures"]}
        if not all(m.lower() in names for m in e_measures):
            continue
        have = {_row_key(r, got["by"], [names[m.lower()] for m in e_measures]) for r in got["rows"]}
        if have == want:
            return True, "rows match"
    if not tried:
        return False, f"no query_metric call on the {spec['cube']} cube"
    return False, f"none of {tried} {spec['cube']} queries returned the expected {len(want)} rows"


@dataclass
class Scored:
    id: str
    question: str
    refusal: bool
    passed: bool
    checks: dict[str, tuple[bool, str]]
    text: str = ""
    confidence: str = ""
    tools: list[str] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    number_retries: int = 0
    seconds: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)
    cost: float | None = None
    error: str | None = None
    could_not_answer: str | None = None
    suggestions: list[str] = field(default_factory=list)
    rewritten_for: list[str] = field(default_factory=list)   # numbers that sent a draft back

    def failed(self) -> list[str]:
        return [f"{k}: {why}" for k, (ok, why) in self.checks.items() if not ok]


def score(q: dict, result, engine) -> dict[str, tuple[bool, str]]:
    checks: dict[str, tuple[bool, str]] = {}
    calls = result.trace.calls
    names = [c.name for c in calls]

    want_conf = _as_list(q.get("expected_confidence"))
    if want_conf:
        got = result.confidence.value
        checks["confidence"] = (got in want_conf, f"got {got}, expected {'/'.join(want_conf)}")

    kpi = q.get("expected_kpi")
    if kpi:
        kpi_calls = [c for c in calls if c.name in ("get_kpi_value", "search_methodology")]
        if kpi == "any":
            ok = bool(kpi_calls)
        else:
            ok = any(c.input.get("kpi_id") == kpi for c in kpi_calls)
        checks["kpi"] = (ok, f"{kpi} not looked up" if not ok else "")

    tool = q.get("expected_tool")
    if tool:
        checks["tool"] = (tool in names, f"{tool} not called" if tool not in names else "")

    spec = q.get("expected_tool_input")
    if spec and engine is not None:
        inputs = [c.input for c in calls if c.name == "query_metric"]
        checks["rows"] = rows_match(engine, spec, inputs)

    facts = q.get("expected_key_facts") or []
    if facts:
        seen = _visible_text(result.text, result.tables)
        missing = []
        for f in facts:
            options = _as_list(f)
            if not any(_norm(str(o)) in seen for o in options):
                missing.append(" / ".join(str(o) for o in options))
        checks["facts"] = (not missing, f"missing: {'; '.join(missing)}" if missing else "")

    # `expected_could_not_answer`: a reason (or list of acceptable ones), or
    # "none" when it must answer. Suggestions are required with any reason the
    # model gives, so the card is never a dead end.
    if "expected_could_not_answer" in q:
        want = [None if r in (None, "none") else r for r in _as_list(q["expected_could_not_answer"]) or [None]]
        got = getattr(result, "could_not_answer", None)
        ok = got in want
        why = f"got {got or 'answered'}, expected {'/'.join(r or 'answered' for r in want)}"
        if ok and got and got != "unverified" and not getattr(result, "suggestions", None):
            ok, why = False, f"{got} with no suggested question"
        checks["reason"] = (ok, "" if ok else why)

    checks["numbers"] = (not result.unverified,
                         f"not from any tool: {', '.join(result.unverified)}" if result.unverified else "")
    return checks


# ------------------------------------------------------------------ running


def run(questions: list[dict], model: str, max_cost: float | None, console,
        effort: str | None = None) -> list[Scored]:
    from .agent import OIRPAgent, SemanticLayer

    layer = SemanticLayer.load(SL / "kpis", SL / "base_prompt.md")
    out: list[Scored] = []
    agent = None
    spent = 0.0
    for i, q in enumerate(questions):
        if max_cost is not None and spent >= max_cost:
            console.print(f"[yellow]Stopped: estimated spend ${spent:.2f} reached --max-cost ${max_cost:.2f}.[/]")
            break
        if agent is None or not q.get("follow_up"):
            agent = OIRPAgent(SL / "kpis", SL / "base_prompt.md", model=model, effort=effort, layer=layer)
        console.print(f"[dim]{i + 1}/{len(questions)}[/] {q['id']} …", end=" ")
        t0 = time.perf_counter()
        try:
            result = agent.chat(q["question"])
        except Exception as e:  # an API error fails this question, not the run
            s = Scored(q["id"], q["question"], bool(q.get("expected_refusal")), False,
                       {"run": (False, f"{type(e).__name__}: {e}")}, seconds=time.perf_counter() - t0,
                       error=f"{type(e).__name__}: {e}")
            out.append(s)
            console.print(f"[red]error[/] {s.error[:120]}")
            if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError"):
                console.print("[red]Stopping: the API key was rejected.[/]")
                break
            if "credit balance" in str(e).lower():
                console.print("[red]Stopping: the account is out of API credit (Plans & Billing in the Console).[/]")
                break
            continue
        seconds = time.perf_counter() - t0
        checks = score(q, result, layer.engine)
        usage = dict(result.trace.usage)
        cost = cost_usd(model, usage)
        spent += cost or 0.0
        s = Scored(
            id=q["id"], question=q["question"], refusal=bool(q.get("expected_refusal")),
            passed=all(ok for ok, _ in checks.values()), checks=checks, text=result.text,
            confidence=result.confidence.value, tools=[c.name for c in result.trace.calls],
            tables=result.tables, unverified=result.unverified, number_retries=result.number_retries,
            seconds=seconds, usage=usage, cost=cost,
            could_not_answer=result.could_not_answer, suggestions=list(result.suggestions),
            rewritten_for=list(result.rewritten_for),
        )
        out.append(s)
        verdict = "[green]pass[/]" if s.passed else "[red]FAIL[/] " + "; ".join(s.failed())[:160]
        console.print(f"{verdict} [dim]({seconds:.0f}s{f', ${cost:.3f}' if cost is not None else ''})[/]")
    return out


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "–"


def summarize(results: list[Scored], model: str) -> dict:
    answerable = [r for r in results if not r.refusal]
    refusals = [r for r in results if r.refusal]
    secs = sorted(r.seconds for r in results if not r.error)
    p95 = secs[min(len(secs) - 1, round(0.95 * (len(secs) - 1)))] if secs else 0.0
    usage: dict[str, int] = {}
    for r in results:
        for k, v in r.usage.items():
            usage[k] = usage.get(k, 0) + v
    costs = [r.cost for r in results if r.cost is not None]
    a_rate = sum(r.passed for r in answerable) / len(answerable) if answerable else 1.0
    r_rate = sum(r.passed for r in refusals) / len(refusals) if refusals else 1.0
    unverified = sum(1 for r in results if r.unverified)
    return {
        "model": model,
        "questions": len(results),
        "passed": sum(r.passed for r in results),
        "answerable": _pct(sum(r.passed for r in answerable), len(answerable)),
        "refusals": _pct(sum(r.passed for r in refusals), len(refusals)),
        "answers_with_unverified_numbers": unverified,
        "number_rewrites": sum(r.number_retries for r in results),
        "tool_calls_mean": round(statistics.mean(len(r.tools) for r in results), 1) if results else 0,
        "seconds_p50": round(statistics.median(secs), 1) if secs else 0,
        "seconds_p95": round(p95, 1),
        "tokens": usage,
        "cost_usd_estimate": round(sum(costs), 3) if costs else None,
        "meets_bar": {
            "answerable": a_rate >= BAR_ANSWERABLE,
            "refusals": r_rate >= BAR_REFUSALS,
            "no_unverified_numbers": unverified == 0,
            "p95_latency": p95 <= BAR_P95_SECONDS,
        },
        "bar": {"answerable": BAR_ANSWERABLE, "refusals": BAR_REFUSALS, "p95_seconds": BAR_P95_SECONDS},
    }


def markdown(summary: dict, results: list[Scored], stamp: str) -> str:
    bar = summary["meets_bar"]
    yes = lambda b: "yes" if b else "**no**"  # noqa: E731
    lines = [
        f"# Eval run {stamp} · {summary['model']}",
        "",
        "| | |", "|---|---|",
        f"| Answerable questions passed | {summary['answerable']} (bar {BAR_ANSWERABLE:.0%}: {yes(bar['answerable'])}) |",
        f"| Refusals passed | {summary['refusals']} (bar {BAR_REFUSALS:.0%}: {yes(bar['refusals'])}) |",
        f"| Answers with unverified numbers | {summary['answers_with_unverified_numbers']} (bar 0: {yes(bar['no_unverified_numbers'])}) |",
        f"| Number-check rewrites | {summary['number_rewrites']} |",
        f"| Tool calls per question (mean) | {summary['tool_calls_mean']} |",
        f"| Latency p50 / p95 | {summary['seconds_p50']} s / {summary['seconds_p95']} s (bar {BAR_P95_SECONDS:.0f} s: {yes(bar['p95_latency'])}) |",
        f"| Tokens | {', '.join(f'{k} {v:,}' for k, v in summary['tokens'].items())} |",
        f"| Estimated cost | {'$%.2f' % summary['cost_usd_estimate'] if summary['cost_usd_estimate'] is not None else 'unknown model price'} |",
        "",
        "| Question | Result | Why it failed |", "|---|---|---|",
    ]
    for r in results:
        why = "; ".join(r.failed()).replace("|", "\\|")
        lines.append(f"| `{r.id}`{' (refusal)' if r.refusal else ''} | {'pass' if r.passed else '**fail**'} | {why} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from rich.console import Console

    from .agent import DEFAULT_EFFORT, DEFAULT_MODEL
    from .kpi_store import KPIStore
    from .prompt_loader import load_semantic_layer

    p = argparse.ArgumentParser(prog="python -m oirp_agent.evals", description=__doc__.split("\n\n")[0])
    p.add_argument("--check", action="store_true", help="validate the question file and expected queries; no model calls")
    p.add_argument("--only", help="comma-separated question ids")
    p.add_argument("--limit", type=int, help="run only the first N questions")
    p.add_argument("--model", default=None, help="model id (default: $OIRP_MODEL or the agent's default)")
    p.add_argument("--effort", default=None,
                   help="low | medium | high | xhigh | max, or none (default: $OIRP_EFFORT or the agent's default)")
    p.add_argument("--max-cost", type=float, default=None, help="stop once the estimated spend reaches this many USD")
    p.add_argument("--questions", type=Path, default=QUESTIONS)
    args = p.parse_args(argv)
    console = Console()

    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        from .__main__ import _load_dotenv
        _load_dotenv(ROOT / ".env")

    questions = load_questions(args.questions)
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    if args.check:
        from .synthetic_warehouse import DEFAULT_DB_PATH, ensure_built
        from .warehouse import WarehouseEngine, load_cubes

        ensure_built(DEFAULT_DB_PATH)
        engine = WarehouseEngine(DEFAULT_DB_PATH, load_cubes(SL / "warehouse"))
        store = KPIStore(load_semantic_layer(SL / "kpis"))
        problems = check_definitions(load_questions(args.questions), engine, store)
        for pr in problems:
            console.print(f"[red]✗[/] {pr}")
        n_rows = sum(1 for q in questions if q.get("expected_tool_input"))
        console.print(f"{len(questions)} questions, {n_rows} with expected queries: "
                      + ("[green]all valid[/]" if not problems else f"[red]{len(problems)} problems[/]"))
        return 1 if problems else 0

    model = args.model or os.environ.get("OIRP_MODEL") or DEFAULT_MODEL
    effort = (args.effort or os.environ.get("OIRP_EFFORT") or DEFAULT_EFFORT or "none").lower()
    effort = None if effort == "none" else effort
    if model not in PRICES:
        console.print(f"[yellow]No price on file for {model}; cost will show as unknown.[/]")
    label = f"{model} · effort {effort or 'default'}"
    console.print(f"Running {len(questions)} questions on [bold]{label}[/]"
                  + (f", stopping at ${args.max_cost:.2f}" if args.max_cost is not None else "") + ".")
    results = run(questions, model, args.max_cost, console, effort=effort)
    summary = summarize(results, label)

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    RESULTS.mkdir(parents=True, exist_ok=True)
    base = RESULTS / f"{stamp}-{model}-{effort or 'default'}"
    base.with_suffix(".json").write_text(json.dumps({
        "summary": summary,
        "results": [{**r.__dict__, "checks": {k: {"ok": ok, "why": why} for k, (ok, why) in r.checks.items()}}
                    for r in results],
    }, indent=1, default=str), encoding="utf-8")
    md = markdown(summary, results, stamp)
    base.with_suffix(".md").write_text(md, encoding="utf-8")

    console.print()
    from rich.markdown import Markdown
    console.print(Markdown(md))
    console.print(f"[dim]Saved {base.with_suffix('.json').relative_to(ROOT)} and .md[/]")
    return 0 if all(summary["meets_bar"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
