"""
LLM-assisted drafter for new verified-value records in the semantic layer.

For a given extracted PDF (in data/extracted/<id>/), this script:

  1. Loads the pages + tables JSON for that PDF
  2. Loads all existing semantic-layer KPI files (so the agent knows the schemas)
  3. Asks Claude (via tool use) to propose new verified-value entries for any
     KPI the PDF covers, each with a verbatim quote anchor from the source text
  4. Validates that every proposed quote_anchor actually appears on the cited page
  5. Writes data/proposed/<pdf_id>.review.md — a human-readable review file
     containing the JSON you'd paste into your KPI files plus prose context

The drafter NEVER edits semantic_layer/kpis/ directly. Human review is the gate.

Usage:
    python scripts/draft_kpi_values.py --pdf nsse_2023_summary
    python scripts/draft_kpi_values.py --all
    python scripts/draft_kpi_values.py --pdf nsse_2023_summary --kpi nsse_high_impact_practices

Options:
    --pdf <id>       PDF id from the manifest (required unless --all).
    --all            Run against every PDF in the extracted/ directory.
    --kpi <id>       Limit to a single KPI (otherwise the agent considers all).
    --model <id>     Override model (default: claude-sonnet-4-6).
    --max-pages <n>  Cap pages sent to the agent (useful for very long PDFs).
    --dry-run        Print the request shape without calling the API.

Cost notes:
    A typical NSSE summary PDF (~20 pages, ~22k tokens of context) costs roughly
    $0.05–0.15 per draft against Sonnet 4.6. The drafter is meant to be run
    once per PDF and then iterated on the review file by hand, not run
    continuously, so the per-run cost matters more than throughput.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Anthropic SDK is optional at module load — fail late so --dry-run works
# without it installed.
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
PROPOSED_DIR = PROJECT_ROOT / "data" / "proposed"
KPI_DIR = PROJECT_ROOT / "semantic_layer" / "kpis"

# Default to Haiku 4.5 for drafting: this is structured tool-use against a clear
# schema, not creative work, so Haiku handles it well at ~5-6x lower cost than
# Sonnet. Override with --model if you want to compare quality.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 8192


# ============================================================================
# Loading helpers
# ============================================================================


def load_extracted_pdf(pdf_id: str) -> dict:
    """Read the extraction outputs for a single PDF id."""
    pdf_dir = EXTRACTED_DIR / pdf_id
    if not pdf_dir.exists():
        raise FileNotFoundError(
            f"No extracted data for {pdf_id!r}. "
            f"Run scripts/extract_pdfs.py --only {pdf_id} first."
        )
    return {
        "id": pdf_id,
        "meta": json.loads((pdf_dir / "meta.json").read_text()),
        "pages": json.loads((pdf_dir / "pages.json").read_text()),
        "tables": json.loads((pdf_dir / "tables.json").read_text()),
    }


def load_kpi_files(only_kpi_id: str | None = None) -> list[dict]:
    """Read every .md file from semantic_layer/kpis/ and return their raw text.

    We don't use the prompt_loader here because we want the raw markdown
    (frontmatter, JSON blocks, prose) — that's exactly what the drafter
    needs to see in order to mimic the schema.
    """
    paths = sorted(KPI_DIR.glob("*.md"))
    if only_kpi_id:
        paths = [p for p in paths if p.stem == only_kpi_id]
        if not paths:
            raise FileNotFoundError(
                f"No KPI file for {only_kpi_id!r} in {KPI_DIR}"
            )
    return [{"path": p, "text": p.read_text(encoding="utf-8")} for p in paths]


def list_extracted_pdfs() -> list[str]:
    if not EXTRACTED_DIR.exists():
        return []
    return sorted(d.name for d in EXTRACTED_DIR.iterdir() if d.is_dir())


# ============================================================================
# Prompt assembly
# ============================================================================


SYSTEM_PROMPT = """You are an institutional-research data assistant helping
draft proposed verified-value entries for a curated semantic layer about
Carleton University's OIRP (Office of Institutional Research and Planning)
data.

You will be given:
  1. The full text of every existing KPI markdown file (your schemas and prose
     conventions to follow).
  2. The extracted pages and tables of one source PDF.

Your job: identify which existing KPIs this PDF contains values for, and for
each, propose new verified-value records that match that KPI's existing JSON
schema. Use the `propose_kpi_value` tool once per proposed record.

CRITICAL RULES (violating these means you should not propose the value):

1. EVERY proposed value MUST come with a `quote_anchor`: a verbatim excerpt
   of 8–25 words from the source page that demonstrates the number is
   supported by the source. If you can't find an excerpt that contains the
   number, do not propose it.

2. EVERY proposed value MUST cite the specific page number it came from.
   For tabular data, also cite the table label (e.g., "Table 4").

3. NEVER invent numbers. If the value is not visible in the page text or
   tables, do not propose it. The point of this drafter is human-reviewable
   grounded proposals — a proposal that turns out to be a hallucination
   wastes the reviewer's time and erodes trust in the pipeline.

4. MATCH the existing KPI's schema. If the existing verified-values block
   uses fields like {year, cohort, comparison_group, value_pct, source}, your
   proposal should use the same fields. Look at the existing records in the
   KPI file as templates.

5. ONLY propose values that are NEW relative to what's already in the KPI
   file. If a record for {year=2023, cohort=first_year, ...} already exists
   verbatim, don't re-propose it. (You may flag corrections to existing
   records via the `flag_correction` tool if you spot a mismatch with the
   source.)

6. For any value where you're uncertain (e.g., the table cell is ambiguous
   or the value requires interpretation), set `confidence` to "medium" or
   "low" and explain in `notes`. The reviewer needs to know what to scrutinize.

7. After all proposals (or if you find none), call the `finish` tool with a
   summary of what you found and what you deliberately did NOT propose.

Tone: direct, factual. The output goes to a markdown review file for a human
to read; write your `notes` and `summary` text to be useful at review time.
"""


def build_kpi_context_block(kpi_files: list[dict]) -> str:
    """Build the KPI-files context. This is the cacheable prefix:
    it's the same across every PDF and every tool turn, so it goes in its
    own content block with cache_control set."""
    parts: list[str] = []
    parts.append("## Existing KPI semantic-layer files\n")
    parts.append(
        "These define the schemas you must match. Each has a frontmatter "
        "block, prose definitions, and one or more `verified-values` JSON "
        "blocks. Your proposals should fit alongside the existing JSON "
        "records in the appropriate KPI's verified-values block.\n\n"
    )
    for kpi in kpi_files:
        parts.append(f"### File: `{kpi['path'].name}`\n\n")
        parts.append("```markdown\n")
        parts.append(kpi["text"])
        parts.append("\n```\n\n")
    return "".join(parts)


def build_pdf_context_block(extracted: dict) -> str:
    """Build the per-PDF context. Different per PDF, so not cached."""
    parts: list[str] = []
    meta = extracted["meta"]
    parts.append(f"## Source PDF: `{extracted['id']}`\n\n")
    parts.append(f"- Title: {meta.get('title')}\n")
    parts.append(f"- Doc type: {meta.get('doc_type')}\n")
    parts.append(f"- Year: {meta.get('year')}\n")
    parts.append(f"- Source URL: {meta.get('source_url')}\n")
    parts.append(f"- Pages: {meta.get('page_count')}\n")
    parts.append(f"- Tables found: {meta.get('n_tables')}\n\n")

    parts.append("### Pages and tables\n\n")
    parts.append(
        "For each page below, you have the full extracted text and any tables "
        "found on it. Tables include `None` cells where the source PDF used "
        "visual padding rather than grid lines — read across the row to "
        "interpret the layout. Some tables span multiple visual columns "
        "(e.g., 'Carleton First-Year' and 'Ontario First-Year' grouped under "
        "a 'First Year' header above them).\n\n"
    )

    for page in extracted["pages"]:
        parts.append(f"#### Page {page['page']}\n\n")
        parts.append("**Text:**\n```\n")
        parts.append(page["text"] or "(no text extracted)")
        parts.append("\n```\n\n")
        if page["tables"]:
            parts.append(f"**Tables on page {page['page']}:**\n\n")
            for t in page["tables"]:
                parts.append(
                    f"- Table {t['table_index']} "
                    f"({t['n_rows']} rows × {t['n_cols']} cols):\n"
                )
                parts.append("  ```json\n")
                parts.append("  " + json.dumps(t["rows"], ensure_ascii=False))
                parts.append("\n  ```\n")
            parts.append("\n")

    parts.append(
        "\n---\n\n"
        "Now: identify which existing KPIs this PDF contains NEW verified "
        "values for, propose them via the `propose_kpi_value` tool (one call "
        "per record), and finish with the `finish` tool. Skip KPIs the PDF "
        "doesn't cover. Skip records that already exist in the KPI files. "
        "Always include a verbatim `quote_anchor` from the source.\n"
    )
    return "".join(parts)


# Kept for backward compat / dry-run estimation.
def build_user_message(extracted: dict, kpi_files: list[dict]) -> str:
    return build_kpi_context_block(kpi_files) + build_pdf_context_block(extracted)


# ============================================================================
# Tool schemas
# ============================================================================

TOOLS: list[dict[str, Any]] = [
    {
        "name": "propose_kpi_value",
        "description": (
            "Propose ONE new verified-value record for ONE KPI. Use the same "
            "field schema as the KPI's existing verified-values block. Every "
            "call MUST include a verbatim quote_anchor from the source page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kpi_id": {
                    "type": "string",
                    "description": (
                        "The kpi_id of the target KPI, matching one of the "
                        "files in semantic_layer/kpis/."
                    ),
                },
                "record": {
                    "type": "object",
                    "description": (
                        "The proposed verified-value record. Match the schema "
                        "of existing records in the target KPI file. MUST "
                        "include a `source` sub-object with at least `file`, "
                        "`page`, and `quote_anchor` fields."
                    ),
                    "additionalProperties": True,
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": (
                        "high = the value is unambiguously stated in source; "
                        "medium = derivable but requires interpretation; "
                        "low = ambiguous, flag for careful reviewer attention."
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Brief reviewer-facing note explaining why this "
                        "record was proposed and any judgment calls made. "
                        "Required for medium/low confidence."
                    ),
                },
            },
            "required": ["kpi_id", "record", "confidence", "notes"],
        },
    },
    {
        "name": "flag_correction",
        "description": (
            "Flag a discrepancy between an existing record in a KPI file and "
            "what the source PDF actually says. Use sparingly — only when "
            "you're confident the existing record is wrong, not just when the "
            "source uses different phrasing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kpi_id": {"type": "string"},
                "existing_value_summary": {
                    "type": "string",
                    "description": "Brief description of the existing record.",
                },
                "discrepancy": {
                    "type": "string",
                    "description": "What the source actually says vs the existing record.",
                },
                "source_quote_anchor": {
                    "type": "string",
                    "description": "Verbatim excerpt from the source supporting the correction.",
                },
                "source_page": {"type": "integer"},
            },
            "required": [
                "kpi_id",
                "existing_value_summary",
                "discrepancy",
                "source_quote_anchor",
                "source_page",
            ],
        },
    },
    {
        "name": "finish",
        "description": (
            "Call this exactly once when you've finished proposing records. "
            "Provide a summary for the reviewer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": (
                        "Reviewer-facing summary: what KPIs this PDF covered, "
                        "how many records you proposed for each, and any "
                        "deliberate omissions (e.g., 'I did not propose "
                        "Ontario consortium values for X because the source "
                        "reports them only as direction, not point values')."
                    ),
                },
            },
            "required": ["summary"],
        },
    },
]


# ============================================================================
# The drafter loop
# ============================================================================


def quote_appears_in_page(quote: str, pages: list[dict], page_no: int) -> bool:
    """Verify that a quote_anchor appears verbatim in the cited page text.

    Whitespace-tolerant: collapses runs of whitespace before comparing, so
    line breaks in the source PDF don't break a perfectly good quote.
    """
    target = next((p for p in pages if p["page"] == page_no), None)
    if not target:
        return False
    haystack = " ".join(target["text"].split())
    needle = " ".join(quote.split())
    return needle.lower() in haystack.lower()


def run_drafter(
    extracted: dict,
    kpi_files: list[dict],
    *,
    model: str,
    max_tokens: int,
    dry_run: bool,
) -> dict:
    """Run one drafter session against one PDF. Returns a result dict."""
    kpi_context = build_kpi_context_block(kpi_files)
    pdf_context = build_pdf_context_block(extracted)

    if dry_run:
        full_message = kpi_context + pdf_context
        return {
            "dry_run": True,
            "estimated_user_message_chars": len(full_message),
            "estimated_user_message_tokens": len(full_message) // 4,
            "estimated_cacheable_chars": len(kpi_context),
            "estimated_per_pdf_chars": len(pdf_context),
            "kpi_files_loaded": [k["path"].name for k in kpi_files],
            "pdf_id": extracted["id"],
        }

    if Anthropic is None:
        raise RuntimeError(
            "anthropic SDK not installed. Run: pip install anthropic"
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set in this terminal. "
            "Run: export $(grep -v '^#' .env | xargs)"
        )

    client = Anthropic()

    proposals: list[dict] = []
    corrections: list[dict] = []
    summary: str | None = None
    cache_metrics = {"cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

    # Two content blocks for the user message:
    #   1. KPI-files context — IDENTICAL across every PDF and every tool turn.
    #      Marked with cache_control so subsequent calls in this run (and
    #      across runs within the cache TTL) read it from cache instead of
    #      paying full ITPM cost.
    #   2. The per-PDF context — different per PDF, not cached.
    initial_user_content = [
        {
            "type": "text",
            "text": kpi_context,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": pdf_context,
        },
    ]
    messages: list[dict] = [{"role": "user", "content": initial_user_content}]

    # System prompt is also identical across all runs — cache it too.
    system_blocks = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # Bounded loop. The drafter normally finishes in 5–20 tool turns
    # depending on PDF richness; cap at 60 to avoid runaway.
    for _ in range(60):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            tools=TOOLS,
            messages=messages,
        )

        # Track cache metrics across turns so we can report the savings.
        usage = response.usage
        cache_metrics["cache_creation_input_tokens"] += getattr(
            usage, "cache_creation_input_tokens", 0
        ) or 0
        cache_metrics["cache_read_input_tokens"] += getattr(
            usage, "cache_read_input_tokens", 0
        ) or 0

        # Persist assistant turn
        messages.append(
            {
                "role": "assistant",
                "content": [
                    block.model_dump() if hasattr(block, "model_dump") else dict(block)
                    for block in response.content
                ],
            }
        )

        if response.stop_reason != "tool_use":
            break

        tool_results: list[dict] = []
        finished = False
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            name = block.name
            tool_input = block.input
            tool_use_id = block.id

            if name == "propose_kpi_value":
                proposals.append(tool_input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(
                            {"status": "recorded", "proposal_count": len(proposals)}
                        ),
                    }
                )
            elif name == "flag_correction":
                corrections.append(tool_input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(
                            {"status": "recorded", "correction_count": len(corrections)}
                        ),
                    }
                )
            elif name == "finish":
                summary = tool_input.get("summary", "")
                finished = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps({"status": "ok"}),
                    }
                )
            else:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps({"error": f"unknown tool: {name}"}),
                        "is_error": True,
                    }
                )

        messages.append({"role": "user", "content": tool_results})
        if finished:
            break

    # Validate quote anchors against page text.
    for p in proposals:
        record = p.get("record", {})
        source = record.get("source") or {}
        quote = source.get("quote_anchor")
        page_no = source.get("page")
        if not quote or page_no is None:
            p["_validation"] = "missing quote_anchor or page"
            continue
        ok = quote_appears_in_page(quote, extracted["pages"], page_no)
        p["_validation"] = "verified" if ok else "QUOTE NOT FOUND ON CITED PAGE"

    return {
        "dry_run": False,
        "pdf_id": extracted["id"],
        "model": model,
        "proposals": proposals,
        "corrections": corrections,
        "summary": summary or "(agent did not call finish)",
        "cache_metrics": cache_metrics,
    }


# ============================================================================
# Review-file rendering
# ============================================================================


def render_review_markdown(extracted: dict, result: dict) -> str:
    """Render a result into a human-readable markdown review file."""
    out: list[str] = []
    meta = extracted["meta"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    out.append(f"# Drafter review: `{extracted['id']}`\n\n")
    out.append(
        f"_Generated {now} by `scripts/draft_kpi_values.py` "
        f"using model `{result['model']}`._\n\n"
    )
    out.append(
        "> **This file is a proposal, not a commit.** Read each proposed "
        "record below, verify the quote anchor against the cited page in the "
        "source PDF, and copy approved JSON entries into the appropriate "
        "`semantic_layer/kpis/<kpi_id>.md` file's verified-values block. "
        "Discard or correct anything that doesn't match the source.\n\n"
    )

    out.append("## Source\n\n")
    out.append(f"- **Title:** {meta.get('title')}\n")
    out.append(f"- **PDF id:** `{extracted['id']}`\n")
    out.append(f"- **Source URL:** {meta.get('source_url')}\n")
    out.append(f"- **Source sha256:** `{meta.get('source_sha256')}`\n")
    out.append(f"- **Pages / tables:** {meta.get('page_count')} / {meta.get('n_tables')}\n\n")

    out.append("## Drafter summary\n\n")
    out.append(f"> {result['summary']}\n\n")

    proposals = result["proposals"]
    corrections = result["corrections"]
    n_verified = sum(1 for p in proposals if p.get("_validation") == "verified")
    n_unverified = len(proposals) - n_verified

    out.append("## Stats\n\n")
    out.append(f"- Proposed records: **{len(proposals)}** ")
    out.append(f"({n_verified} verified, {n_unverified} flagged for review)\n")
    out.append(f"- Flagged corrections: **{len(corrections)}**\n\n")

    if proposals:
        # Group by kpi_id for readability.
        by_kpi: dict[str, list[dict]] = {}
        for p in proposals:
            by_kpi.setdefault(p["kpi_id"], []).append(p)

        out.append("## Proposed verified-value records\n\n")
        for kpi_id in sorted(by_kpi.keys()):
            out.append(f"### KPI: `{kpi_id}`\n\n")
            for i, p in enumerate(by_kpi[kpi_id], start=1):
                conf = p.get("confidence", "?")
                conf_badge = {
                    "high": "🟢 high",
                    "medium": "🟡 medium",
                    "low": "🔴 low",
                }.get(conf, conf)
                validation = p.get("_validation", "(not validated)")
                if validation == "verified":
                    val_badge = "✅ quote verified"
                elif validation.startswith("QUOTE NOT FOUND"):
                    val_badge = "❌ **QUOTE NOT FOUND ON CITED PAGE — do not accept without manual check**"
                else:
                    val_badge = f"⚠️ {validation}"

                out.append(f"#### Proposal {i} — confidence: {conf_badge}\n\n")
                out.append(f"- {val_badge}\n\n")
                out.append("**Proposed JSON record** (copy into the verified-values block):\n\n")
                out.append("```json\n")
                out.append(json.dumps(p["record"], indent=2, ensure_ascii=False))
                out.append("\n```\n\n")
                if p.get("notes"):
                    out.append(f"**Notes:** {p['notes']}\n\n")
                out.append("---\n\n")

    if corrections:
        out.append("## Flagged corrections\n\n")
        out.append(
            "_The drafter flagged these as potential discrepancies between "
            "your existing KPI files and the source PDF. Verify carefully._\n\n"
        )
        for i, c in enumerate(corrections, start=1):
            out.append(f"### Correction {i} — KPI `{c['kpi_id']}`\n\n")
            out.append(f"- **Existing:** {c['existing_value_summary']}\n")
            out.append(f"- **Discrepancy:** {c['discrepancy']}\n")
            out.append(f"- **Source page:** {c['source_page']}\n")
            out.append(f"- **Source quote:** {c['source_quote_anchor']!r}\n\n")
            out.append("---\n\n")

    return "".join(out)


# ============================================================================
# Entry point
# ============================================================================


def load_dotenv_if_present() -> None:
    """Inline .env loader so this script Just Works after the user does
    the .env setup we documented earlier."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--pdf", help="PDF id from the manifest")
    g.add_argument("--all", action="store_true", help="Run against every extracted PDF")

    parser.add_argument("--kpi", help="Limit to a single KPI by id (otherwise consider all)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model id (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max tokens per response (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the prompt but don't call the API. Prints what would be sent.",
    )
    args = parser.parse_args()

    load_dotenv_if_present()

    if args.all:
        pdf_ids = list_extracted_pdfs()
        if not pdf_ids:
            print("error: no PDFs in data/extracted/. Run scripts/extract_pdfs.py first.")
            return 1
    else:
        pdf_ids = [args.pdf]

    PROPOSED_DIR.mkdir(parents=True, exist_ok=True)
    kpi_files = load_kpi_files(only_kpi_id=args.kpi)
    if not kpi_files:
        print(f"error: no KPI files found in {KPI_DIR}")
        return 1

    n_done = 0
    n_failed = 0

    for pdf_id in pdf_ids:
        try:
            extracted = load_extracted_pdf(pdf_id)
        except FileNotFoundError as e:
            print(f"  ✗ {pdf_id}: {e}")
            n_failed += 1
            continue

        print(f"  → drafting against {pdf_id} ({extracted['meta'].get('page_count')} pages)...")
        try:
            result = run_drafter(
                extracted,
                kpi_files,
                model=args.model,
                max_tokens=args.max_tokens,
                dry_run=args.dry_run,
            )
        except Exception as e:
            print(f"  ✗ {pdf_id}: drafter failed: {type(e).__name__}: {e}")
            n_failed += 1
            continue

        if result.get("dry_run"):
            print(
                f"    [dry run] user message would be ~{result['estimated_user_message_chars']:,} "
                f"chars (~{result['estimated_user_message_tokens']:,} tokens), "
                f"loading {len(result['kpi_files_loaded'])} KPI files."
            )
            n_done += 1
            continue

        review = render_review_markdown(extracted, result)
        out_path = PROPOSED_DIR / f"{pdf_id}.review.md"
        out_path.write_text(review)
        n_proposals = len(result["proposals"])
        n_verified = sum(1 for p in result["proposals"] if p.get("_validation") == "verified")
        print(
            f"    ✓ {n_proposals} proposals ({n_verified} verified), "
            f"{len(result['corrections'])} corrections "
            f"→ {out_path.relative_to(PROJECT_ROOT)}"
        )
        cm = result.get("cache_metrics") or {}
        cache_read = cm.get("cache_read_input_tokens", 0)
        cache_write = cm.get("cache_creation_input_tokens", 0)
        if cache_read or cache_write:
            print(
                f"    cache: {cache_read:,} tokens read from cache "
                f"(saved from rate limit), {cache_write:,} tokens written"
            )
        n_done += 1

    print()
    print(f"done. drafted={n_done}  failed={n_failed}")
    return 0 if n_failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
