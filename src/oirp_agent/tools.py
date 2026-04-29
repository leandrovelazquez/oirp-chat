"""
Tool schemas and implementations for the agent.

Three tools, each backed by the KPIStore:

  - get_kpi_value: structured lookup against verified records
  - search_methodology: keyword search over prose sections
  - list_kpis: discovery / metadata

The schemas follow the Anthropic tool-use format. Each tool's `description`
is part of the agent's grounding — the agent reads these to decide when to
call which tool, so the descriptions matter as much as the implementations.
"""

from __future__ import annotations

from typing import Any

from .kpi_store import KPIStore


# ---------- Tool schemas (sent to the API) ----------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_kpi_value",
        "description": (
            "Look up verified KPI values from the in-memory store. This is your "
            "PRIMARY tool. Use it for any specific number or directional finding. "
            "If it returns an empty list, the value is not in the verified store — "
            "do NOT estimate; instead, refuse and direct the user to the relevant "
            "OIRP source.\n\n"
            "Pass a kpi_id (use list_kpis if unsure which one) and an optional "
            "`filters` object for narrowing. Common filter keys include: year, "
            "cohort (e.g., 'first_year' / 'final_year'), comparison_group "
            "(e.g., 'carleton'), metric_variant, hip, indicator, theme, "
            "program_length, scope, period."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kpi_id": {
                    "type": "string",
                    "description": "The KPI to query. Use list_kpis if unsure.",
                },
                "filters": {
                    "type": "object",
                    "description": (
                        "Optional exact-match filters. Keys depend on the KPI; "
                        "consult the KPI's verified-values block in the system "
                        "prompt for the available fields."
                    ),
                    "additionalProperties": True,
                },
            },
            "required": ["kpi_id"],
        },
    },
    {
        "name": "search_methodology",
        "description": (
            "Search prose sections of the KPI files for methodology, definitions, "
            "caveats, item-level drivers, headline findings, or comparison context. "
            "Use this for 'what does X mean', 'how is Y calculated', 'what are the "
            "caveats of Z', and similar qualitative questions. Returns matching "
            "sections with their KPI source.\n\n"
            "Note: this is keyword search, not semantic search, so prefer specific "
            "terms over abstract phrasing. Optionally scope to a single KPI."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for in prose sections.",
                },
                "kpi_id": {
                    "type": "string",
                    "description": "Optional: restrict the search to one KPI.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max sections to return (default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_kpis",
        "description": (
            "Return summary metadata for every KPI in the semantic layer: "
            "kpi_id, domain, status, metric_type, source_survey, and a one-line "
            "summary. Use this when the user's question doesn't clearly map to a "
            "KPI you already know about, or when the user asks 'what can I ask "
            "you about'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ---------- Tool implementations ----------


class ToolDispatcher:
    """Wires tool calls to the underlying store. Tracks which tools fired
    and what they returned, for confidence-tier computation."""

    def __init__(self, store: KPIStore) -> None:
        self.store = store

    def dispatch(self, tool_name: str, tool_input: dict) -> dict:
        """Execute a tool call. Returns a JSON-serializable result dict."""
        if tool_name == "get_kpi_value":
            return self._get_kpi_value(tool_input)
        if tool_name == "search_methodology":
            return self._search_methodology(tool_input)
        if tool_name == "list_kpis":
            return self._list_kpis()
        return {"error": f"Unknown tool: {tool_name}"}

    def _get_kpi_value(self, tool_input: dict) -> dict:
        kpi_id = tool_input.get("kpi_id")
        if not kpi_id:
            return {"error": "kpi_id is required", "records": []}
        filters = tool_input.get("filters") or {}
        records = self.store.query_records(kpi_id=kpi_id, filters=filters)
        return {
            "kpi_id": kpi_id,
            "filters": filters,
            "match_count": len(records),
            "records": records,
        }

    def _search_methodology(self, tool_input: dict) -> dict:
        query = tool_input.get("query", "")
        kpi_id = tool_input.get("kpi_id")
        top_k = int(tool_input.get("top_k", 5))
        sections = self.store.search_prose(query=query, kpi_id=kpi_id, top_k=top_k)
        return {
            "query": query,
            "kpi_id": kpi_id,
            "match_count": len(sections),
            "sections": [
                {"kpi_id": s.kpi_id, "header": s.header, "text": s.text}
                for s in sections
            ],
        }

    def _list_kpis(self) -> dict:
        return {"kpis": self.store.list_kpis()}
