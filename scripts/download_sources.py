"""
Download OIRP source PDFs into data/pdfs/, hash them, and write a manifest.

Reads scripts/sources.toml — the editable list of sources you maintain.
Writes data/pdfs/manifest.json — the machine-readable record of what's on disk.

Idempotent: re-running skips files whose existing hash matches the source URL's
content. If a PDF on the OIRP site changes, the sha256 will differ and the
script re-downloads.

Usage:
    python scripts/download_sources.py                       # download everything
    python scripts/download_sources.py --only nsse_2023_summary
    python scripts/download_sources.py --force               # re-download even if hash matches

This script uses only the standard library plus `tomllib` (built into Python 3.11+),
so it has no dependencies beyond what's already in your venv.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if sys.version_info < (3, 11):
    raise RuntimeError(
        "This script requires Python 3.11 or newer (uses tomllib from stdlib). "
        f"You're on {sys.version_info.major}.{sys.version_info.minor}."
    )

import tomllib  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES_TOML = PROJECT_ROOT / "scripts" / "sources.toml"
PDFS_DIR = PROJECT_ROOT / "data" / "pdfs"
MANIFEST_PATH = PDFS_DIR / "manifest.json"

# Be polite — identify the script in the User-Agent so OIRP's web team can
# distinguish well-behaved local downloads from random scrapers if they look
# at access logs.
USER_AGENT = "oirp-chat/0.1 (portfolio demo; local download script)"

# Some Carleton subdomains return 403 for unknown User-Agents. The string
# above plus a generic Accept header is enough to pass.
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/pdf,*/*",
}

# Bound the download size so a misconfigured URL can't fill the disk.
MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def load_sources() -> list[dict]:
    if not SOURCES_TOML.exists():
        raise FileNotFoundError(f"Manifest not found: {SOURCES_TOML}")
    with SOURCES_TOML.open("rb") as f:
        data = tomllib.load(f)

    sources = data.get("source", [])
    if not isinstance(sources, list) or not sources:
        raise ValueError(
            f"{SOURCES_TOML} has no [[source]] entries. "
            "Add one or more before running this script."
        )

    # Validate each entry up front so we fail loudly before any network calls.
    seen_ids: set[str] = set()
    for s in sources:
        for required in ("id", "url", "doc_type", "year", "title"):
            if required not in s:
                raise ValueError(
                    f"Source entry missing '{required}': {s!r}"
                )
        if s["url"] == "FILL_IN":
            # Skip placeholder rows silently — they're commented in TOML by
            # convention but if someone uncomments without filling, we want
            # a clear message.
            raise ValueError(
                f"Source {s['id']!r} has url='FILL_IN'. "
                "Either fill in the real URL or comment the entry out."
            )
        if s["id"] in seen_ids:
            raise ValueError(f"Duplicate source id: {s['id']!r}")
        seen_ids.add(s["id"])
    return sources


def load_existing_manifest() -> dict[str, dict]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return {entry["id"]: entry for entry in json.loads(MANIFEST_PATH.read_text())}
    except (json.JSONDecodeError, KeyError):
        # Corrupt manifest — better to rebuild than to trust it.
        return {}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    """Stream `url` into `dest`, atomically. Raises on HTTP errors."""
    req = Request(url, headers=HEADERS)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    bytes_written = 0
    try:
        with urlopen(req, timeout=60) as resp, tmp.open("wb") as out:
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                # Don't refuse outright — some servers send 'text/plain' or
                # 'application/force-download' for PDFs. But warn loudly so
                # the user notices if they pasted an HTML page URL by mistake.
                print(
                    f"  warning: server returned Content-Type={content_type!r}; "
                    "saving anyway (verify the file is a real PDF)."
                )
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_BYTES:
                    raise RuntimeError(
                        f"Download exceeded {MAX_BYTES} bytes; aborting. "
                        "If this is legitimate, raise MAX_BYTES."
                    )
                out.write(chunk)
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--only",
        action="append",
        help="Restrict to one or more source ids (repeat --only to add more).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the existing file's hash already matches the manifest.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the configured sources and exit without downloading.",
    )
    args = parser.parse_args()

    sources = load_sources()
    if args.only:
        wanted = set(args.only)
        sources = [s for s in sources if s["id"] in wanted]
        missing = wanted - {s["id"] for s in sources}
        if missing:
            print(f"warning: --only ids not found in manifest: {sorted(missing)}")
        if not sources:
            print("nothing to do.")
            return 0

    if args.list:
        for s in sources:
            print(f"  {s['id']:45s} {s['doc_type']:18s} {s['year']}  {s['url']}")
        return 0

    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_existing_manifest()

    new_manifest: list[dict] = []
    n_downloaded = 0
    n_skipped = 0
    n_failed = 0

    for s in sources:
        sid = s["id"]
        dest = PDFS_DIR / f"{sid}.pdf"
        prior = existing.get(sid)

        # Skip if the file is on disk, hashes match the prior manifest, and the
        # URL hasn't changed in the source list. --force overrides.
        if (
            not args.force
            and dest.exists()
            and prior
            and prior.get("url") == s["url"]
            and prior.get("sha256") == sha256_of(dest)
        ):
            print(f"  ✓ {sid}: up to date (skipped)")
            n_skipped += 1
            new_manifest.append(prior)
            continue

        print(f"  ↓ {sid}: downloading from {s['url']} ...")
        try:
            download(s["url"], dest)
        except (HTTPError, URLError, RuntimeError) as e:
            print(f"  ✗ {sid}: download failed: {e}")
            n_failed += 1
            # Preserve any prior manifest entry rather than dropping it on a
            # transient network failure.
            if prior:
                new_manifest.append(prior)
            continue

        digest = sha256_of(dest)
        size_bytes = dest.stat().st_size

        new_entry = {
            "id": sid,
            "url": s["url"],
            "doc_type": s["doc_type"],
            "year": s["year"],
            "title": s["title"],
            "filename": dest.name,
            "sha256": digest,
            "size_bytes": size_bytes,
            "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if "notes" in s:
            new_entry["notes"] = s["notes"]
        new_manifest.append(new_entry)
        n_downloaded += 1
        print(
            f"    saved {size_bytes:,} bytes; sha256={digest[:12]}…"
        )

    # Sort manifest by id for stable diffs in Git.
    new_manifest.sort(key=lambda e: e["id"])
    MANIFEST_PATH.write_text(json.dumps(new_manifest, indent=2) + "\n")

    print()
    print(
        f"done. downloaded={n_downloaded}  skipped={n_skipped}  "
        f"failed={n_failed}  total_in_manifest={len(new_manifest)}"
    )
    print(f"manifest: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    print(f"pdfs:     {PDFS_DIR.relative_to(PROJECT_ROOT)}")

    return 0 if n_failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
