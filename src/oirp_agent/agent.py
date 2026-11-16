"""
The agent loop.

We use the lower-level Anthropic Messages API and implement the tool loop by
hand rather than using the SDK's `tool_runner` convenience wrapper. The manual
loop is more lines of code, but for a portfolio project the explicitness is
the point: anyone reading agent.py can see exactly how tool-calling, conversation
history, and confidence tracking fit together.

Architecture per turn:

  1. Append the user's message to conversation history.
  2. Send messages.create() with the system prompt, tool schemas, and history.
  3. If stop_reason == "tool_use", execute every tool_use block in the
     response, package the results as tool_result content blocks, and loop.
  4. If stop_reason == "end_turn", we have the final assistant message.
  5. Check every number in it against the tool results (numbers.py). If one
     isn't there, send the model one rewrite request; then drop the failed
     draft and the request from history, compute the confidence tier and return.

A caller can pass `on_progress` to chat() to hear each step as it happens (a
model call, a tool call and its result, the number check). The web page uses
it to show what the assistant is doing while it works. The answer's text is
not streamed: it is shown only once its numbers have passed the check.

The system prompt is assembled once at agent construction (it includes all
KPI files concatenated). Conversation history accumulates across user turns
but resets when the caller starts a new conversation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from anthropic import Anthropic

from . import cannot_answer
from .confidence import ConfidenceTier, TurnTrace
from .kpi_store import KPIStore
from .numbers import check_answer, model_payload, retry_feedback
from .prompt_loader import (
    KPIDocument,
    assemble_system_prompt,
    load_semantic_layer,
)
from .tools import TOOL_SCHEMAS, WAREHOUSE_TOOLS, ToolDispatcher
from .warehouse import Cube, WarehouseEngine, load_cubes


# Default model. Easy to override at construction time (OIRP_MODEL for the
# web server, --model for the CLI and the evals).
DEFAULT_MODEL = "claude-sonnet-5-5"
# Thinking counts toward max_tokens on the 5.x models, so leave room for it
# as well as the short answer.
DEFAULT_MAX_TOKENS = 16000
# How much the model thinks (output_config.effort): low | medium | high | xhigh
# | max. Set explicitly because the defaults differ by model (Sonnet 5.5: high,
# Haiku 5.5: medium). None sends no effort, for models that don't take one.
DEFAULT_EFFORT: str | None = "medium"

# What the user sees when the model's safety checks decline a request
# (stop_reason "refusal"); the history gets the same text, so the
# conversation can go on.
REFUSAL_TEXT = ("The model declined to answer this question, so there is no answer to show. "
                "Try asking it another way.")

# Safety bound on the inner tool loop to avoid runaway calls. Warehouse
# questions can take describe -> query -> corrected query, so leave headroom.
MAX_TOOL_ROUNDS = 10

# The number check: one rewrite when an answer holds a number no tool
# returned, with a few tool rounds in case the fix needs another lookup.
MAX_NUMBER_RETRIES = 1
RETRY_TOOL_ROUNDS = 3

# Receives one progress event (a plain dict with a "step" key) at a time.
ProgressFn = Callable[[dict], None]


@dataclass
class SemanticLayer:
    """Everything loaded once and shared read-only across conversations."""

    documents: list[KPIDocument]
    store: KPIStore
    cubes: list[Cube]
    engine: WarehouseEngine | None
    system_prompt: str

    @classmethod
    def load(
        cls,
        kpi_dir: Path,
        base_prompt_path: Path,
        warehouse_dir: Path | None = None,
        warehouse_db: Path | None = None,
        build_if_missing: bool = True,
    ) -> "SemanticLayer":
        documents = load_semantic_layer(kpi_dir)
        store = KPIStore(documents)
        cubes: list[Cube] = []
        engine: WarehouseEngine | None = None
        if warehouse_dir is None:
            warehouse_dir = kpi_dir.parent / "warehouse"
        if warehouse_dir.exists():
            cubes = load_cubes(warehouse_dir)
        if cubes:
            from .synthetic_warehouse import DEFAULT_DB_PATH, ensure_built

            db = warehouse_db or DEFAULT_DB_PATH
            if build_if_missing:
                ensure_built(db)
            if db.exists():
                engine = WarehouseEngine(db, cubes)
        system_prompt = assemble_system_prompt(
            base_prompt_path, documents,
            [(c.name, c.raw_markdown) for c in cubes] if engine else None,
        )
        return cls(documents, store, cubes, engine, system_prompt)


@dataclass
class TurnResult:
    """Outcome of one user-message → assistant-response cycle."""

    text: str
    confidence: ConfidenceTier
    trace: TurnTrace
    raw_stop_reason: str | None = None
    # The number check (numbers.py): how many numbers in `text` were checked
    # against tool results, which ones no tool result supports (empty when the
    # answer passed), and how many rewrites it took.
    numbers_checked: int = 0
    unverified: list[str] = field(default_factory=list)
    number_retries: int = 0
    # Why it couldn't answer (cannot_answer.REASONS), or None when it did, and
    # up to three questions it can answer instead.
    could_not_answer: str | None = None
    suggestions: list[str] = field(default_factory=list)
    # Next questions worked out from the last warehouse query (followups.py).
    follow_ups: list[str] = field(default_factory=list)
    # The numbers that sent a draft back for a rewrite (diagnostics, for the evals).
    rewritten_for: list[str] = field(default_factory=list)

    @property
    def tables(self) -> list[dict]:
        return self.trace.tables


@dataclass
class OIRPAgent:
    semantic_layer_dir: Path
    base_prompt_path: Path
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    effort: str | None = DEFAULT_EFFORT
    # Pass a pre-loaded layer to share it across agents (the web server does).
    layer: SemanticLayer | None = None

    # Filled in __post_init__:
    documents: list[KPIDocument] = field(init=False)
    store: KPIStore = field(init=False)
    engine: WarehouseEngine | None = field(init=False)
    dispatcher: ToolDispatcher = field(init=False)
    system_prompt: str = field(init=False)
    client: Anthropic | None = None
    history: list[dict] = field(init=False, default_factory=list)
    # Everything a number in an answer may come from: the user's messages, tool
    # inputs, and tool results as the model saw them. Kept for the conversation,
    # so a follow-up may repeat a number an earlier tool returned.
    evidence: list[str] = field(init=False, default_factory=list)
    # Set for the duration of one chat() call.
    _progress: ProgressFn | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.layer is None:
            self.layer = SemanticLayer.load(self.semantic_layer_dir, self.base_prompt_path)
        self.documents = self.layer.documents
        self.store = self.layer.store
        self.engine = self.layer.engine
        self.dispatcher = ToolDispatcher(self.store, self.engine)
        self.system_prompt = self.layer.system_prompt
        if self.client is None:
            self.client = Anthropic()
        self.history = []
        self.evidence = []

    # ----- public API -----

    def chat(self, user_message: str, on_progress: ProgressFn | None = None) -> TurnResult:
        """Run one user turn through the tool loop, check its numbers, return it.

        If the answer holds a number no tool returned, the model gets one chance
        to rewrite it (with a short tool budget). The failed attempt and the
        feedback are then dropped from history, so later turns see only the
        answer that was shown.

        `on_progress`, if given, is called with each step as it happens:
          {"step": "model", "phase": "read" | "tools_back" | "rewrite"}
          {"step": "tool", "name": ..., "label": ...}           before a tool runs
          {"step": "tool_done", "name": ..., "summary": ..., "error": bool}
          {"step": "check", "checked": n, "missing": [...]}     after each draft
        """
        self._progress = on_progress
        try:
            return self._chat(user_message)
        finally:
            self._progress = None

    def _chat(self, user_message: str) -> TurnResult:
        self.history.append({"role": "user", "content": user_message})
        self.evidence.append(user_message)
        trace = TurnTrace()
        tools = TOOL_SCHEMAS if self.engine is not None else [
            t for t in TOOL_SCHEMAS if t["name"] not in WAREHOUSE_TOOLS
        ]

        retries = 0
        rewritten_for: list[str] = []   # the numbers that sent each draft back
        failed_at: list[int] = []
        stop, out_of_rounds = self._tool_loop(trace, tools, MAX_TOOL_ROUNDS, first_phase="read")
        while True:
            # The "can't answer" block is read off and never shown or checked.
            text, reason, suggestions = cannot_answer.split(_extract_text(self.history[-1]["content"]))
            # Evidence: the system prompt (the hand-verified published layer and
            # the rules it states, such as the 0.3 effect-size threshold), then
            # everything the user typed and every tool returned.
            checked, missing = check_answer(text, [self.system_prompt, *self.evidence])
            self._notify(step="check", checked=checked, missing=missing,
                         final=not missing or retries >= MAX_NUMBER_RETRIES)
            if not missing or retries >= MAX_NUMBER_RETRIES:
                break
            retries += 1
            rewritten_for.extend(missing)
            failed_at.append(len(self.history) - 1)
            self.history.append({"role": "user", "content": retry_feedback(missing)})
            stop, out_of_rounds = self._tool_loop(trace, tools, RETRY_TOOL_ROUNDS, first_phase="rewrite")

        # Drop each failed answer and the feedback that followed it (newest
        # first, so earlier indices stay valid). What remains alternates
        # correctly: the message before a failed answer is a user turn, and the
        # one after the feedback is the rewrite.
        for i in reversed(failed_at):
            del self.history[i:i + 2]
        # Thinking blocks are bound to the history they were written after
        # ("preserved thinking" on the 5.x models): the rewrite's blocks were
        # written with the failed draft in front of them, so replaying them
        # now would be rejected. Removing the trailing run of thinking blocks
        # keeps every earlier block valid; the rewrite's text and tool calls stay.
        if failed_at:
            _strip_thinking(self.history[failed_at[0]:])

        # A "no data" or "limit" label on an answer that shows warehouse numbers
        # contradicts itself (seen on Haiku 5.5, which labels correct warehouse
        # answers). The rows are on screen, so it answered: drop the label.
        if reason in ("no_data", "limit") and _warehouse_rows_shown(trace):
            reason, suggestions = None, []
        could_not = reason or _code_reason(trace, missing, out_of_rounds)
        return TurnResult(
            text=text,
            confidence=trace.confidence,
            trace=trace,
            raw_stop_reason=stop,
            numbers_checked=checked,
            unverified=missing,
            number_retries=retries,
            # The model's reason first; the code's own reasons only fill a gap.
            could_not_answer=could_not,
            suggestions=suggestions,
            # Follow-ups only after an answer; a "can't answer" has its suggestions.
            follow_ups=[] if could_not else trace.follow_ups,
            rewritten_for=rewritten_for,
        )

    def reset(self) -> None:
        """Drop conversation history (semantic layer & client are kept)."""
        self.history = []
        self.evidence = []

    # ----- internals -----

    def _notify(self, **event: Any) -> None:
        """Report a progress event. A broken listener never breaks the answer."""
        if self._progress is None:
            return
        try:
            self._progress(event)
        except Exception:  # noqa: BLE001 - progress is best effort
            pass

    def _tool_loop(
        self, trace: TurnTrace, tools: list[dict], max_rounds: int, first_phase: str = "read",
    ) -> tuple[str | None, bool]:
        """Call the model until it answers in text.

        Returns the last stop_reason, and whether the tool budget ran out (the
        last round forbade tools, so the model had to answer with what it had).
        """
        last_stop_reason: str | None = None
        out_of_rounds = False
        for round_no in range(max_rounds + 1):
            out_of_rounds = round_no == max_rounds
            self._notify(step="model", phase=first_phase if round_no == 0 else "tools_back")
            # On the last round, forbid tools so the turn always ends in text
            # (`none` is accepted on every model; forced `any`/`tool` is not on 5.5).
            extra: dict[str, Any] = {"tool_choice": {"type": "none"}} if round_no == max_rounds else {}
            if self.effort:
                extra["output_config"] = {"effort": self.effort}
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=tools,
                messages=self.history,
                **extra,
            )

            trace.add_usage(getattr(response, "usage", None))

            # A safety decline: show a plain message instead of whatever partial
            # content came back, and keep the history valid for the next turn.
            if response.stop_reason == "refusal":
                self.history.append({"role": "assistant", "content": [{"type": "text", "text": REFUSAL_TEXT}]})
                last_stop_reason = "refusal"
                break

            # Persist the assistant turn (model output) to history regardless of
            # stop_reason — the API requires the full prior assistant message
            # when we send back tool_result blocks.
            self.history.append(
                {"role": "assistant", "content": _serialize_content(response.content)}
            )
            last_stop_reason = response.stop_reason

            if response.stop_reason == "tool_use":
                tool_result_blocks = self._execute_tool_calls(response.content, trace)
                # Tool results are returned in a single user turn.
                self.history.append({"role": "user", "content": tool_result_blocks})
                continue

            # Any other stop_reason = we're done with this turn.
            break
        return last_stop_reason, out_of_rounds

    def _execute_tool_calls(
        self,
        assistant_content: list[Any],
        trace: TurnTrace,
    ) -> list[dict]:
        """Run every tool_use block in the assistant message; return tool_result blocks."""
        results: list[dict] = []
        for block in assistant_content:
            block_type = getattr(block, "type", None)
            if block_type != "tool_use":
                continue

            name = block.name
            tool_input = block.input
            tool_use_id = block.id

            self._notify(step="tool", name=name, label=describe_call(name, tool_input))
            result = self.dispatcher.dispatch(name, tool_input)

            # Record for confidence tracking.
            if name == "get_kpi_value":
                trace.record_get_kpi_value(tool_input, result)
            elif name == "search_methodology":
                trace.record_search_methodology(tool_input, result)
            elif name == "list_kpis":
                trace.record_list_kpis(tool_input, result)
            elif name == "query_metric":
                trace.record_query_metric(tool_input, result)
            elif name == "compare_metric":
                trace.record_compare_metric(tool_input, result)
            elif name == "describe_cube":
                trace.record_describe_cube(tool_input, result)
            else:
                trace.record_generic(name, tool_input, result)
            self._notify(step="tool_done", name=name, error="error" in result,
                         summary=describe_outcome(name, result))

            # What the model sees: no SQL, and warehouse values as display
            # strings only. The same text is what its numbers are checked against.
            content = model_payload(name, result)
            self.evidence.append(json.dumps(tool_input, default=str))
            self.evidence.append(content)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    **({"is_error": True} if "error" in result else {}),
                }
            )
        return results


def _warehouse_rows_shown(trace: TurnTrace) -> bool:
    """Did a warehouse query or comparison this turn return values that are shown?"""
    return any(c.name in ("query_metric", "compare_metric") and c.record_count > 0 for c in trace.calls)


def _code_reason(trace: TurnTrace, missing: list[str], out_of_rounds: bool) -> str | None:
    """A "can't answer" reason the code can tell for itself, whatever the model wrote."""
    if missing:
        return "unverified"
    if out_of_rounds:
        return "limit"
    # The warehouse answered, but every cell it returned is suppressed, and no
    # published value was found either: the number asked for can't be shown.
    shown = [c for c in trace.calls
             if c.name in ("query_metric", "compare_metric", "get_kpi_value") and c.record_count > 0]
    all_hidden = [c for c in trace.calls if c.name == "query_metric" and c.table and c.record_count == 0]
    if all_hidden and not shown:
        return "limit"
    return None


# ---------- plain-English progress lines ----------


def _short(level: Any) -> str:
    """'1st Academic Unit.Faculty' -> 'Faculty'."""
    return str(level).rsplit(".", 1)[-1]


def _values(v: Any) -> str:
    return " or ".join(map(str, v)) if isinstance(v, list) else str(v)


def describe_call(name: str, tool_input: dict | None) -> str:
    """What a tool call is about to do, in words a non-analyst can follow."""
    ti = tool_input or {}
    if name == "query_metric":
        measures = ", ".join(map(str, ti.get("measures") or [])) or "a measure"
        text = f"Asking the {ti.get('cube', 'warehouse')} cube for {measures}"
        if ti.get("by"):
            text += " by " + " and ".join(_short(b) for b in ti["by"])
        filters = ti.get("filters") or {}
        if filters:
            text += ": " + ", ".join(f"{_short(k)} {_values(v)}" for k, v in filters.items())
        return text
    if name == "compare_metric":
        by = (" by " + " and ".join(_short(b) for b in ti["by"])) if ti.get("by") else ""
        if ti.get("kind") == "share":
            return f"Working out each share of {ti.get('measure', 'the total')}{by} in the {ti.get('cube', '')} cube"
        return (f"Working out the change in {ti.get('measure', 'the measure')} from "
                f"{ti.get('from', '?')} to {ti.get('to', '?')}{by}")
    if name == "describe_cube":
        if ti.get("dimension"):
            return f"Looking up the members of {ti['dimension']} in the {ti.get('cube', '')} cube".replace("  ", " ")
        if ti.get("cube"):
            return f"Reading the {ti['cube']} cube's measures and dimensions"
        return "Listing the warehouse cubes"
    if name == "get_kpi_value":
        kpi = str(ti.get("kpi_id", "an indicator")).replace("_", " ")
        filters = ti.get("filters") or {}
        narrow = ", ".join(_values(v).replace("_", " ") for v in filters.values())
        return f"Looking up the published figure for {kpi}" + (f" ({narrow})" if narrow else "")
    if name == "search_methodology":
        return f"Reading the definitions for “{ti.get('query', '')}”"
    if name == "list_kpis":
        return "Listing the published indicators"
    return f"Running {name}"


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def describe_outcome(name: str, result: dict) -> str:
    """What came back from a tool call, briefly. Counts only, never values."""
    if "error" in result:
        return "That didn't fit the cube; adjusting the query" if name in ("query_metric", "compare_metric") \
            else "That didn't work; trying another way"
    if name == "compare_metric":
        text = _n(len(result.get("rows", [])), "row")
        if result.get("not_shown"):
            text += f", {result['not_shown']} not shown (small cells)"
        return text + " · worked out by the engine, not the model"
    if name == "query_metric":
        rows = result.get("rows", [])
        text = _n(len(rows), "row")
        if result.get("suppressed_cells"):
            text += f", {result['suppressed_cells']} hidden as fewer than ten students"
        if result.get("data_as_of"):
            text += f" · data as of {result['data_as_of']}"
        return text
    if name == "get_kpi_value":
        n = len(result.get("records", []))
        return f"Found {_n(n, 'published value')}" if n else "Not in the published data"
    if name == "search_methodology":
        return f"Found {_n(len(result.get('sections', [])), 'section')}"
    if name == "list_kpis":
        return _n(len(result.get("kpis", [])), "indicator")
    return "Done"


# ---------- helpers for serializing API objects into history ----------


def _serialize_content(content: list[Any]) -> list[dict]:
    """Turn the API's response content blocks into plain dicts for history reuse.

    The Anthropic SDK returns typed objects; we round-trip through plain dicts
    so the same structure can be sent back as part of `messages` on the next
    request.
    """
    out = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            out.append({"type": "text", "text": block.text})
        elif block_type == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
        else:
            # thinking / redacted_thinking (on by default on the 5.x models) and
            # any future block type: passed back exactly as received, even when
            # the thinking text is empty, since its signature is what counts.
            d = (
                block.model_dump(mode="json", exclude_none=True)
                if hasattr(block, "model_dump")
                else dict(vars(block))
            )
            out.append(d)
    return out


def _strip_thinking(messages: list[dict]) -> None:
    """Remove thinking blocks from these messages, in place (a trailing run only)."""
    for m in messages:
        if m["role"] == "assistant" and isinstance(m["content"], list):
            m["content"] = [b for b in m["content"] if b.get("type") not in ("thinking", "redacted_thinking")] \
                or [{"type": "text", "text": "(no text)"}]


def _extract_text(content: list[dict]) -> str:
    """Pull all text blocks out of a serialized assistant message."""
    parts = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n\n".join(parts).strip()
