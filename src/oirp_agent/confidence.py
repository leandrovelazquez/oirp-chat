"""
Confidence tier tracking.

After each agent turn, we look at which tools fired and what they returned
to assign a confidence tier:

  - HIGH:    get_kpi_value returned at least one record, OR query_metric
             returned at least one unsuppressed row (a governed query against
             the synthetic warehouse).
  - MEDIUM:  search_methodology returned matches, but no get_kpi_value records.
             OR only discovery tools were used (list_kpis / describe_cube).
  - LOW:     A get_kpi_value or query_metric call was made but returned no
             usable value (zero records, an error, or only suppressed cells),
             AND nothing else backed up the answer. The agent should have
             refused to give a number; flag for review.

Separately, `sources` records WHICH layer a turn's numbers came from --
"published" (real, cited) and/or "synthetic" (demo warehouse) -- so the UI can
label synthetic answers.
  - NONE:    No tools fired. For an institutional research agent, this should
             be rare and is a signal that the agent answered from memory.
             We don't block on it (the agent might legitimately answer a
             definitional/meta question), but we surface it.

The tier is informational — surfaced to the user and logged for evals — not
a hard gate. The agent is instructed via system prompt to refuse rather than
guess, and the tier helps a reviewer verify it actually did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .followups import follow_ups
from .numbers import compare_table, published_table, warehouse_table

# Tools whose results carry numbers (a hit makes a turn HIGH confidence).
VALUE_TOOLS = ("get_kpi_value", "query_metric", "compare_metric")
WAREHOUSE_VALUE_TOOLS = ("query_metric", "compare_metric")


class ConfidenceTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class ToolCallTrace:
    name: str
    input: dict
    result_summary: str  # short human-readable summary
    record_count: int = 0  # for get_kpi_value / query_metric (usable rows)
    section_count: int = 0  # for search_methodology
    detail: str | None = None  # e.g. compiled SQL for query_metric
    table: dict | None = None  # the numbers as the page draws them (numbers.py)
    follow_ups: list[str] = field(default_factory=list)  # next questions, from the query (followups.py)


@dataclass
class TurnTrace:
    """Per-turn record of which tools fired and how they behaved."""

    calls: list[ToolCallTrace] = field(default_factory=list)
    # Token usage summed over every API request in the turn (for the evals'
    # cost report): input_tokens, output_tokens, cache_creation_input_tokens,
    # cache_read_input_tokens, requests.
    usage: dict[str, int] = field(default_factory=dict)

    def add_usage(self, usage: object) -> None:
        self.usage["requests"] = self.usage.get("requests", 0) + 1
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            self.usage[key] = self.usage.get(key, 0) + int(getattr(usage, key, 0) or 0)

    def record_get_kpi_value(self, tool_input: dict, result: dict) -> None:
        records = result.get("records", [])
        self.calls.append(
            ToolCallTrace(
                name="get_kpi_value",
                input=tool_input,
                result_summary=(
                    f"kpi_id={tool_input.get('kpi_id')!r}, "
                    f"match_count={len(records)}"
                ),
                record_count=len(records),
                table=published_table(tool_input, result),
            )
        )

    def record_search_methodology(self, tool_input: dict, result: dict) -> None:
        sections = result.get("sections", [])
        self.calls.append(
            ToolCallTrace(
                name="search_methodology",
                input=tool_input,
                result_summary=(
                    f"query={tool_input.get('query')!r}, "
                    f"kpi_id={tool_input.get('kpi_id')!r}, "
                    f"match_count={len(sections)}"
                ),
                section_count=len(sections),
            )
        )

    def record_list_kpis(self, tool_input: dict, result: dict) -> None:
        self.calls.append(
            ToolCallTrace(
                name="list_kpis",
                input=tool_input,
                result_summary=f"kpi_count={len(result.get('kpis', []))}",
            )
        )

    def record_query_metric(self, tool_input: dict, result: dict) -> None:
        if "error" in result:
            self.calls.append(ToolCallTrace(
                name="query_metric", input=tool_input,
                result_summary=f"cube={tool_input.get('cube')!r} ERROR: {result['error'][:160]}",
            ))
            return
        rows = result.get("rows", [])
        usable = sum(1 for r in rows if not r.get("suppressed"))
        measures = ", ".join(m["name"] for m in result.get("measures", []))
        by = f" by {', '.join(result['by'])}" if result.get("by") else ""
        filt = ", ".join(f"{k}={v}" for k, v in (result.get("filters") or {}).items())
        filt = f" | {filt}" if filt else ""
        supp = f" ({result['suppressed_cells']} suppressed)" if result.get("suppressed_cells") else ""
        stale = " STALE" if result.get("stale") else ""
        self.calls.append(ToolCallTrace(
            name="query_metric", input=tool_input,
            result_summary=(
                f"[synthetic] {result.get('cube')}: {measures}{by}{filt} -> "
                f"{len(rows)} rows{supp}, as of {result.get('data_as_of')}{stale}"
            ),
            record_count=usable,
            detail=result.get("sql"),
            table=warehouse_table(result),
            follow_ups=follow_ups(result),
        ))

    def record_compare_metric(self, tool_input: dict, result: dict) -> None:
        if "error" in result:
            self.calls.append(ToolCallTrace(
                name="compare_metric", input=tool_input,
                result_summary=f"cube={tool_input.get('cube')!r} ERROR: {result['error'][:160]}",
            ))
            return
        rows = result.get("rows", [])
        usable = sum(1 for r in rows if "not shown" not in (r.get("change"), r.get("share")))
        if result.get("kind") == "change":
            what = f"change in {result.get('measure')} along {result.get('along')}, {result.get('from')} -> {result.get('to')}"
        else:
            what = f"share of {result.get('measure')} by {', '.join(result.get('by') or [])}"
        by = f" by {', '.join(result['by'])}" if result.get("by") and result.get("kind") == "change" else ""
        self.calls.append(ToolCallTrace(
            name="compare_metric", input=tool_input,
            result_summary=f"[synthetic] {result.get('cube')}: {what}{by} -> {len(rows)} rows, as of {result.get('data_as_of')}",
            record_count=usable,
            detail="\n\n".join(result.get("sql") or []),
            table=compare_table(result),
        ))

    def record_describe_cube(self, tool_input: dict, result: dict) -> None:
        what = tool_input.get("cube") or "all cubes"
        if tool_input.get("dimension"):
            what += f" / {tool_input['dimension']}"
        self.calls.append(ToolCallTrace(
            name="describe_cube", input=tool_input,
            result_summary=f"{what}" + (f" ERROR: {result['error'][:120]}" if "error" in result else ""),
        ))

    @property
    def tables(self) -> list[dict]:
        """The numbers this turn's tools returned, in call order, ready to draw."""
        return [c.table for c in self.calls if c.table]

    @property
    def follow_ups(self) -> list[str]:
        """Next questions from the turn's last warehouse query that returned rows."""
        for c in reversed(self.calls):
            if c.name == "query_metric" and c.table:
                return list(c.follow_ups)
        return []

    @property
    def sources(self) -> list[str]:
        out = []
        if any(c.name == "get_kpi_value" and c.record_count > 0 for c in self.calls):
            out.append("published")
        if any(c.name in WAREHOUSE_VALUE_TOOLS and c.record_count > 0 for c in self.calls):
            out.append("synthetic")
        return out

    def record_generic(self, name: str, tool_input: dict, result: dict) -> None:
        """Fallback for any tool we add later."""
        self.calls.append(
            ToolCallTrace(
                name=name,
                input=tool_input,
                result_summary=str(result)[:200],
            )
        )

    @property
    def confidence(self) -> ConfidenceTier:
        if not self.calls:
            return ConfidenceTier.NONE

        value_tools = VALUE_TOOLS
        any_kpi_value_hit = any(
            c.name in value_tools and c.record_count > 0 for c in self.calls
        )
        any_kpi_value_miss = any(
            c.name in value_tools and c.record_count == 0 for c in self.calls
        )
        any_methodology_hit = any(
            c.name == "search_methodology" and c.section_count > 0 for c in self.calls
        )
        only_discovery = all(c.name in ("list_kpis", "describe_cube") for c in self.calls)

        if any_kpi_value_hit:
            return ConfidenceTier.HIGH
        if any_methodology_hit:
            return ConfidenceTier.MEDIUM
        if only_discovery:
            return ConfidenceTier.MEDIUM
        if any_kpi_value_miss:
            return ConfidenceTier.LOW
        return ConfidenceTier.NONE
