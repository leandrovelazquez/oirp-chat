"""
In-memory store for verified KPI records and prose sections.

This is what the agent's tools query against. Two indexes:

  - records: list of dicts (one per JSON entry, tagged with kpi_id)
  - prose_sections: list of (kpi_id, header, text) tuples, derived by splitting
    each KPI document on H2 headers (## ...). Used by search_methodology.

The query interface is intentionally simple: filter records by exact-match
key/value pairs. The agent already has the schema in its system prompt, so it
knows which keys exist; the store doesn't need to be schema-aware.

In a production system, both indexes would be backed by a real database
(records → SQLite/Postgres; prose_sections → pgvector with proper embeddings).
The store here is an honest minimum that proves the architecture and can be
swapped without touching the agent or tool layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .prompt_loader import KPIDocument


# Split prose on H2 headers. We keep the header as part of each section.
_H2_SPLIT_RE = re.compile(r"\n(?=## )")


@dataclass
class ProseSection:
    kpi_id: str
    header: str  # e.g., "## Caveats and Methodological Notes"
    text: str  # full section body including header


class KPIStore:
    def __init__(self, documents: list[KPIDocument]) -> None:
        self.documents = documents
        self.records: list[dict] = []
        self.prose_sections: list[ProseSection] = []
        self._build_indexes()

    def _build_indexes(self) -> None:
        for doc in self.documents:
            self.records.extend(doc.all_records)
            self.prose_sections.extend(self._split_prose(doc))

    @staticmethod
    def _split_prose(doc: KPIDocument) -> list[ProseSection]:
        sections = _H2_SPLIT_RE.split(doc.prose)
        out = []
        for section in sections:
            section = section.strip()
            if not section:
                continue
            # Treat the first line as the header (whether or not it starts with ##).
            first_line, _, _ = section.partition("\n")
            out.append(
                ProseSection(
                    kpi_id=doc.kpi_id,
                    header=first_line.strip(),
                    text=section,
                )
            )
        return out

    # ----- record queries -----

    def query_records(
        self,
        kpi_id: str | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        """Return records matching the given kpi_id and exact-match filters.

        `filters` does shallow exact-match comparison on top-level keys. Nested
        keys (e.g. "source.page") are not supported in this minimum version —
        the agent typically filters on flat keys like year, cohort, hip,
        comparison_group, variant.
        """
        out = []
        filters = filters or {}
        for record in self.records:
            if kpi_id is not None and record.get("_kpi_id") != kpi_id:
                continue
            if all(record.get(k) == v for k, v in filters.items()):
                out.append(record)
        return out

    # ----- prose search -----

    def search_prose(
        self,
        query: str,
        kpi_id: str | None = None,
        top_k: int = 5,
    ) -> list[ProseSection]:
        """Naive keyword scoring across prose sections.

        TODO(production): replace with pgvector + Voyage/Cohere embeddings.
        For a portfolio demo, keyword scoring is honest enough to validate the
        architecture; it gets swapped without touching the agent or tool layer.
        """
        terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
        if not terms:
            return []

        scored: list[tuple[int, ProseSection]] = []
        for section in self.prose_sections:
            if kpi_id is not None and section.kpi_id != kpi_id:
                continue
            text_lower = section.text.lower()
            score = sum(text_lower.count(term) for term in terms)
            if score > 0:
                scored.append((score, section))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [sec for _, sec in scored[:top_k]]

    # ----- discovery -----

    def list_kpis(self) -> list[dict]:
        """Return KPI summaries for the list_kpis tool."""
        out = []
        for doc in self.documents:
            # First non-empty line of prose after the H1 is usually the definition.
            summary = self._first_definition_line(doc.prose)
            out.append(
                {
                    "kpi_id": doc.kpi_id,
                    "domain": doc.domain,
                    "status": doc.status,
                    "metric_type": doc.metric_type,
                    "source_survey": doc.source_survey,
                    "summary": summary,
                }
            )
        return out

    @staticmethod
    def _first_definition_line(prose: str) -> str:
        """Pull a short summary out of the prose (first paragraph after Definition)."""
        m = re.search(r"## Definition\s*\n+([^\n]+(?:\n[^\n#]+)*)", prose)
        if m:
            paragraph = m.group(1).strip()
            # Truncate to ~250 chars for the listing.
            if len(paragraph) > 250:
                paragraph = paragraph[:247].rsplit(" ", 1)[0] + "..."
            return paragraph
        return ""
