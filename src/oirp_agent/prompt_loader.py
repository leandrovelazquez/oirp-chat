"""
Parse semantic-layer markdown files into structured KPIDocument objects.

Each KPI file has:
  - YAML frontmatter (--- ... ---) with kpi_id, status, etc.
  - Markdown prose
  - Zero or more ```json fenced blocks containing verified values

This module is responsible for:
  1. Walking the kpis/ directory
  2. Splitting each file into frontmatter / prose / JSON blocks
  3. Returning typed KPIDocument records ready for indexing or prompt assembly
  4. Assembling the full system prompt by stitching base_prompt + KPI files
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# Frontmatter delimiter used at the top of every KPI markdown file.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Fenced JSON code blocks. We capture only the JSON body, not the fence.
_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


@dataclass
class KPIDocument:
    """One parsed KPI markdown file."""

    kpi_id: str
    domain: str
    status: str  # "verified" | "partial" | "stub" | "deprecated"
    metric_type: str | None
    source_survey: str | None
    raw_markdown: str
    prose: str  # markdown body with JSON blocks stripped out
    json_blocks: list[list[dict]] = field(default_factory=list)
    source_path: Path | None = None

    @property
    def all_records(self) -> list[dict]:
        """Flatten all JSON blocks into a single list, tagged with kpi_id."""
        out = []
        for block_idx, block in enumerate(self.json_blocks):
            for record in block:
                tagged = dict(record)
                tagged["_kpi_id"] = self.kpi_id
                tagged["_block_index"] = block_idx
                out.append(tagged)
        return out


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body) for a markdown file with YAML frontmatter.

    Files without frontmatter return ({}, text).
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_yaml = m.group(1)
    body = text[m.end() :]
    fm = yaml.safe_load(fm_yaml) or {}
    if not isinstance(fm, dict):
        raise ValueError(f"Frontmatter is not a mapping: {fm!r}")
    return fm, body


def _extract_json_blocks(body: str) -> tuple[list[list[dict]], str]:
    """Pull all ```json fenced blocks out of `body`.

    Returns a tuple of (parsed_blocks, prose_with_blocks_removed).
    Each parsed block is expected to be a JSON array; if it's a single object,
    we wrap it in a 1-element list for consistency.
    """
    blocks: list[list[dict]] = []
    for m in _JSON_BLOCK_RE.finditer(body):
        raw = m.group(1).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse JSON block at offset {m.start()}: {e}\n"
                f"Block content was:\n{raw[:500]}"
            ) from e
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError(
                f"JSON block must be an array or object; got {type(parsed).__name__}"
            )
        blocks.append(parsed)

    # Replace blocks with a placeholder so prose still reads coherently.
    prose = _JSON_BLOCK_RE.sub("[verified-values block — see structured store]", body)
    return blocks, prose


def load_kpi_document(path: Path) -> KPIDocument:
    """Parse a single KPI markdown file."""
    raw = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(raw)
    blocks, prose = _extract_json_blocks(body)

    if "kpi_id" not in fm:
        raise ValueError(f"{path}: frontmatter missing required 'kpi_id'")

    return KPIDocument(
        kpi_id=fm["kpi_id"],
        domain=fm.get("domain", "unspecified"),
        status=fm.get("status", "unspecified"),
        metric_type=fm.get("metric_type"),
        source_survey=fm.get("source_survey"),
        raw_markdown=raw,
        prose=prose,
        json_blocks=blocks,
        source_path=path,
    )


def load_semantic_layer(kpi_dir: Path) -> list[KPIDocument]:
    """Walk a directory of KPI markdown files and return parsed documents.

    Files are loaded in alphabetical order so the system prompt is reproducible.
    """
    paths = sorted(p for p in kpi_dir.glob("*.md") if p.is_file())
    if not paths:
        raise FileNotFoundError(f"No .md files found in {kpi_dir}")
    return [load_kpi_document(p) for p in paths]


def assemble_system_prompt(
    base_prompt_path: Path,
    documents: list[KPIDocument],
    cube_documents: list[tuple[str, str]] | None = None,
) -> str:
    """Fill base_prompt.md's placeholders.

    {{KPI_DOCUMENTS}}       every published-layer KPI file
    {{WAREHOUSE_DOCUMENTS}} every synthetic-warehouse cube file, as
                            (cube name, raw markdown) pairs

    Files are concatenated as-is (full markdown, including frontmatter) so the
    agent sees the same authoring format the human author wrote.
    """
    base = base_prompt_path.read_text(encoding="utf-8")
    if "{{KPI_DOCUMENTS}}" not in base:
        raise ValueError(
            f"{base_prompt_path}: missing {{KPI_DOCUMENTS}} placeholder"
        )

    chunks = []
    for doc in documents:
        chunks.append(f"\n\n## KPI: `{doc.kpi_id}` (status: {doc.status})\n\n")
        chunks.append(doc.raw_markdown)
    out = base.replace("{{KPI_DOCUMENTS}}", "".join(chunks))

    if "{{WAREHOUSE_DOCUMENTS}}" in out:
        wchunks = []
        for name, raw in cube_documents or []:
            wchunks.append(f"\n\n## Cube: `{name}` (SYNTHETIC)\n\n")
            wchunks.append(raw)
        out = out.replace(
            "{{WAREHOUSE_DOCUMENTS}}",
            "".join(wchunks) or "\n(No synthetic warehouse is loaded in this session.)\n",
        )
    return out
