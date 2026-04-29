"""
Confidence tier tracking.

After each agent turn, we look at which tools fired and what they returned
to assign a confidence tier:

  - HIGH:    get_kpi_value returned at least one record.
  - MEDIUM:  search_methodology returned matches, but no get_kpi_value records.
             OR list_kpis was the only tool used (discovery turn).
  - LOW:     A get_kpi_value call was made but returned zero records, AND
             no methodology search backed up the answer. The agent should
             have refused to give a number; flag for review.
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
    record_count: int = 0  # for get_kpi_value
    section_count: int = 0  # for search_methodology


@dataclass
class TurnTrace:
    """Per-turn record of which tools fired and how they behaved."""

    calls: list[ToolCallTrace] = field(default_factory=list)

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

        any_kpi_value_hit = any(
            c.name == "get_kpi_value" and c.record_count > 0 for c in self.calls
        )
        any_kpi_value_miss = any(
            c.name == "get_kpi_value" and c.record_count == 0 for c in self.calls
        )
        any_methodology_hit = any(
            c.name == "search_methodology" and c.section_count > 0 for c in self.calls
        )
        only_list_kpis = all(c.name == "list_kpis" for c in self.calls)

        if any_kpi_value_hit:
            return ConfidenceTier.HIGH
        if any_methodology_hit:
            return ConfidenceTier.MEDIUM
        if only_list_kpis:
            return ConfidenceTier.MEDIUM
        if any_kpi_value_miss:
            return ConfidenceTier.LOW
        return ConfidenceTier.NONE
