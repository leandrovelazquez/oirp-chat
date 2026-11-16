"""
Follow-up questions, worked out from the query, not written by the model.

After an answer from the warehouse, the page offers up to three next questions
as buttons. They come from the shape of the last governed query and the cube's
`roles` (which dimension is time, which is faculty), so they are always
answerable and always about the same measure:

  - "Break this down by faculty."   when the query wasn't split by faculty;
  - "Same for the 2023 cohort."     when one time value was asked for: the one before;
  - "Show the trend over …"         when the query wasn't already over time.

They're sent to the assistant as ordinary questions in the same conversation,
so "this" means the answer the user just read.
"""

from __future__ import annotations

import re
from typing import Any

_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_SHORT_YEAR = re.compile(r"(?<=/)(\d{2})\b")
MAX_FOLLOW_UPS = 3


def previous(value: Any) -> str | None:
    """The time value one year earlier: Fall 2025 -> Fall 2024, 2025/26 -> 2024/25, 2024 -> 2023."""
    text = str(value)
    if not _YEAR.search(text):
        return None
    text = _YEAR.sub(lambda m: str(int(m.group(1)) - 1), text)
    return _SHORT_YEAR.sub(lambda m: f"{(int(m.group(1)) - 1) % 100:02d}", text)


def _dim(ref: str) -> str:
    return ref.removesuffix(" (dimension)").split(".")[0].lower()


def follow_ups(result: dict) -> list[str]:
    """Up to three next questions for a successful `query_metric` result."""
    roles = result.get("roles") or {}
    if not roles or not result.get("rows") or "error" in result:
        return []
    by = {_dim(b) for b in result.get("by") or []}
    defaults = {k.lower() for k in (result.get("applied_defaults") or {})}
    filters = {k: v for k, v in (result.get("filters") or {}).items() if k.lower() not in defaults}
    times = [t for t in roles.get("time", [])]
    out: list[str] = []

    faculty = roles.get("faculty")
    if faculty and _dim(faculty) not in by:
        out.append("Break this down by faculty.")

    # One time value asked for (and not grouped by time): offer the one before.
    over_time = any(_dim(t) in by for t in times)
    if not over_time:
        for k, v in filters.items():
            if _dim(k) in {_dim(t) for t in times} and not isinstance(v, list):
                prev = previous(v)
                if prev:
                    out.append(f"Same for {roles.get('time_say', '{}').format(prev)}.")
                break

    if not over_time and roles.get("trend"):
        out.append(roles["trend"])
    return out[:MAX_FOLLOW_UPS]
