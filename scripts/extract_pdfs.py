"""
Extract every PDF in data/pdfs/manifest.json into machine-readable form.

For each PDF, this script writes to data/extracted/<pdf_id>/:

  - pages.json     — list of {page, text, tables[]} records, one per page
  - tables.json    — flat list of all tables found, with page references
  - meta.json      — extraction metadata (source sha256, extraction timestamp,
                      tool versions, page count)
  - page-NN.png    — rendered image of any page that contains a table, at
                      150 DPI. Used for human review of table-extraction
                      quality and (later) for vision-model fallback when
                      pdfplumber mangles a table.

Idempotent: re-running skips PDFs whose meta.json's source_sha256 matches the
current manifest. Pass --force to re-extract regardless. Pass --only <id> to
extract a single PDF.

Dependencies (already declared in pyproject.toml as an optional extra you
need to install):

    pip install pdfplumber pypdfium2

pypdfium2 is used for the PNG renderings; pdfplumber handles text + tables.

Usage:
    python scripts/extract_pdfs.py
    python scripts/extract_pdfs.py --only nsse_2023_summary
    python scripts/extract_pdfs.py --force
    python scripts/extract_pdfs.py --no-images   # skip PNG rendering (faster)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Imports we depend on. Fail fast with a useful message if missing.
try:
    import pdfplumber
except ImportError:
    print(
        "error: pdfplumber not installed.\n"
        "       run: pip install pdfplumber pypdfium2",
        file=sys.stderr,
    )
    raise SystemExit(1)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDFS_DIR = PROJECT_ROOT / "data" / "pdfs"
MANIFEST_PATH = PDFS_DIR / "manifest.json"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"

# DPI for rendered page images. 150 is a sweet spot: legible for human review
# and large enough that a vision model can read the table cells, without
# producing 5MB+ PNGs for every page.
RENDER_DPI = 150


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        print(
            f"error: {MANIFEST_PATH} not found.\n"
            "       run scripts/download_sources.py first.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return json.loads(MANIFEST_PATH.read_text())


def needs_extraction(entry: dict, force: bool) -> bool:
    """True if we should (re-)run extraction for this manifest entry."""
    if force:
        return True
    out_dir = EXTRACTED_DIR / entry["id"]
    meta_path = out_dir / "meta.json"
    if not meta_path.exists():
        return True
    try:
        meta = json.loads(meta_path.read_text())
    except json.JSONDecodeError:
        return True
    return meta.get("source_sha256") != entry.get("sha256")


def extract_one(entry: dict, render_images: bool) -> dict:
    """Run extraction for a single PDF. Returns a summary dict."""
    pdf_path = PDFS_DIR / entry["filename"]
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF missing on disk: {pdf_path}")

    out_dir = EXTRACTED_DIR / entry["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    pages_records: list[dict] = []
    all_tables: list[dict] = []
    pages_with_tables: list[int] = []
    page_count = 0

    print(f"  ↻ {entry['id']}: extracting...")
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page_number_zero_indexed, page in enumerate(pdf.pages):
            page_no = page_number_zero_indexed + 1

            # Text. Use a tolerance that handles columnar layouts reasonably.
            # x_tolerance=2 keeps adjacent words from glomming together;
            # y_tolerance=3 keeps line breaks where the layout intends them.
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""

            # Tables. extract_tables() returns a list of tables, each a list
            # of rows, each a list of cell strings (or None for empty cells).
            raw_tables = page.extract_tables() or []
            page_tables: list[dict] = []
            for table_idx, raw in enumerate(raw_tables):
                # Skip degenerate "tables" that are really just a stray ruled
                # line — pdfplumber sometimes returns 1x1 or empty results.
                if not raw or len(raw) < 2:
                    continue
                cleaned = [
                    [(cell.strip() if isinstance(cell, str) else cell) for cell in row]
                    for row in raw
                ]
                table_record = {
                    "page": page_no,
                    "table_index": table_idx,
                    "n_rows": len(cleaned),
                    "n_cols": max(len(r) for r in cleaned) if cleaned else 0,
                    "rows": cleaned,
                }
                page_tables.append(table_record)
                all_tables.append(table_record)

            if page_tables:
                pages_with_tables.append(page_no)

            pages_records.append(
                {
                    "page": page_no,
                    "text": text,
                    "n_tables": len(page_tables),
                    "tables": page_tables,
                }
            )

    # Write structured outputs.
    (out_dir / "pages.json").write_text(
        json.dumps(pages_records, indent=2, ensure_ascii=False) + "\n"
    )
    (out_dir / "tables.json").write_text(
        json.dumps(all_tables, indent=2, ensure_ascii=False) + "\n"
    )

    # Render PNGs for pages with tables, for review / vision fallback.
    rendered = 0
    if render_images and pages_with_tables:
        try:
            import pypdfium2 as pdfium  # noqa: PLC0415 — lazy import on purpose
        except ImportError:
            print(
                "    note: pypdfium2 not installed; skipping PNG rendering. "
                "       run: pip install pypdfium2"
            )
        else:
            doc = pdfium.PdfDocument(pdf_path)
            try:
                # pdfium's scale is in points: 72 dpi default × scale_factor
                scale = RENDER_DPI / 72
                for page_no in pages_with_tables:
                    page = doc[page_no - 1]
                    pil_image = page.render(scale=scale).to_pil()
                    out_path = out_dir / f"page-{page_no:03d}.png"
                    pil_image.save(out_path)
                    rendered += 1
            finally:
                doc.close()

    # Write extraction metadata last (its presence signals a successful run).
    meta = {
        "id": entry["id"],
        "source_filename": entry["filename"],
        "source_sha256": entry["sha256"],
        "source_url": entry["url"],
        "doc_type": entry["doc_type"],
        "year": entry["year"],
        "title": entry["title"],
        "page_count": page_count,
        "n_tables": len(all_tables),
        "pages_with_tables": pages_with_tables,
        "images_rendered": rendered,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_versions": {
            "pdfplumber": getattr(pdfplumber, "__version__", "unknown"),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    return {
        "id": entry["id"],
        "page_count": page_count,
        "n_tables": len(all_tables),
        "pages_with_tables": len(pages_with_tables),
        "images_rendered": rendered,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--only",
        action="append",
        help="Restrict to one or more PDF ids (repeat --only to add more).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even if the existing extraction matches the source sha256.",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip rendering PNGs for pages with tables (faster, smaller output).",
    )
    args = parser.parse_args()

    manifest = load_manifest()
    if args.only:
        wanted = set(args.only)
        manifest = [e for e in manifest if e["id"] in wanted]
        missing = wanted - {e["id"] for e in manifest}
        if missing:
            print(f"warning: --only ids not in manifest: {sorted(missing)}")
        if not manifest:
            print("nothing to do.")
            return 0

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    n_done = 0
    n_skipped = 0
    n_failed = 0
    summaries: list[dict] = []

    for entry in manifest:
        if not needs_extraction(entry, args.force):
            print(f"  ✓ {entry['id']}: extraction up to date (skipped)")
            n_skipped += 1
            continue
        try:
            summary = extract_one(entry, render_images=not args.no_images)
        except Exception as e:
            print(f"  ✗ {entry['id']}: extraction failed: {type(e).__name__}: {e}")
            n_failed += 1
            continue
        n_done += 1
        summaries.append(summary)
        print(
            f"    pages={summary['page_count']}  "
            f"tables={summary['n_tables']}  "
            f"pages_with_tables={summary['pages_with_tables']}  "
            f"images={summary['images_rendered']}"
        )

    print()
    print(f"done. extracted={n_done}  skipped={n_skipped}  failed={n_failed}")
    print(f"output: {EXTRACTED_DIR.relative_to(PROJECT_ROOT)}")

    return 0 if n_failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
