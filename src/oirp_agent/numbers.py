"""
Numbers: how they are written, checked and shown.

Three jobs, all deterministic, all here so there is one place to read and test:

1. **Display strings.** Tools format their own numbers (``1,234``, ``85.3%``,
   ``fewer than 10``) and the model is told to copy them verbatim. The model
   never formats, rounds or converts a value itself.

2. **The number check.** "The model never supplies a number" is enforced, not
   just requested: every number-like token in an answer must match a number
   from governed material: a tool result, the system prompt (the hand-verified
   published layer and the rules it states), or what the user typed. The agent
   retries once with feedback when one doesn't, and flags the answer if it
   still doesn't. What it catches is a number that appears nowhere: invented,
   misremembered, or worked out (a difference, a total, a share).

   What is deliberately *not* checked, because it is context rather than a
   measurement: small whole numbers (0-10: list markers, "Years After 1",
   "3-year programs"), plausible years and year spans (2024, 2024-25), a
   scale's range from zero ("scored 0–60"), and
   numbers glued to letters or underscores (1st, Q3, ``budget_2024_25``).
   A number may be rounded from a tool value (86.94 -> 86.9 or 87), but a
   difference, sum or average the model worked out itself fails.

3. **Tables from tool results.** The page draws the numbers from what the
   tools returned, never from the model's prose, so a wrong sentence cannot
   change a number on screen.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

# ---------------------------------------------------------------- display


def display_value(value: Any, unit: str | None, *, suppressed: bool = False, threshold: int = 10) -> str:
    """Format one value the way every surface shows it."""
    if suppressed:
        return f"fewer than {threshold}"
    if value is None:
        return "–"
    if not isinstance(value, (int, float)):
        return str(value)
    if unit == "percent":
        return f"{value:.1f}%"
    if unit == "gpa_12pt":
        return f"{value:.2f}"
    if unit in ("students", "applicants", "people", "rows", "count"):
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


# ---------------------------------------------------------------- the check

# A number, optionally with thousands separators and decimals, optionally a
# currency sign before and a %/pp/k/M/B after. Not glued to letters, digits,
# underscores or a decimal point on either side.
_NUM = re.compile(
    r"(?<![A-Za-z0-9_.\-/])"
    r"(?P<cur>\$)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<suf>\s?(?:%|pp\b|pts?\b|points?\b)|[kKMB]\b)?"
    r"(?![A-Za-z0-9_])"
)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_YEAR_SPAN = re.compile(r"\b(?:19|20)\d{2}\s?[-–/]\s?(?:(?:19|20)?\d{2})\b")
# A scale's range from zero ("a 0–60 scale", "0 to 100") is a definition, not a
# measurement; a range of percentages ("0–60%") is still checked.
_SCALE_RANGE = re.compile(r"(?<![\d.,])\b0\s?(?:[-–]|to)\s?\d{1,3}\b(?!\s?%|[.,]\d)")
_ISO_OR_SPAN = re.compile(rf"{_DATE.pattern}|{_YEAR_SPAN.pattern}|{_SCALE_RANGE.pattern}")
_SCALE = {"k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9}


def _tokens(text: str) -> list[tuple[str, float, int, float]]:
    """(token as written, value, decimals, scale) for every number in `text`."""
    out = []
    for m in _NUM.finditer(text):
        raw = m.group("num")
        value = float(raw.replace(",", ""))
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        suf = (m.group("suf") or "").strip()
        out.append((m.group(0).strip(), value, decimals, _SCALE.get(suf, 1.0)))
    return out


def evidence_numbers(texts: Iterable[str]) -> tuple[set[float], set[str]]:
    """Every number that appears in the evidence, plus the literal dates in it.

    Fractions are also taken as percentages (a record holding 0.27 supports
    "27%"), since a tool may store a share either way.
    """
    values: set[float] = set()
    dates: set[str] = set()
    for t in texts:
        dates.update(_DATE.findall(t))
        for _, v, _, scale in _tokens(_DATE.sub(" ", t)):
            values.add(v * scale)
            if 0 < v < 1:
                values.add(round(v * 100, 6))
    return values, dates


def _exempt(value: float, decimals: int, token: str) -> bool:
    if decimals == 0 and value <= 10 and "%" not in token and "$" not in token:
        return True
    if decimals == 0 and 1990 <= value <= 2035 and "," not in token and "%" not in token:
        return True  # a year is context, not a measurement
    return False


def check_answer(answer: str, evidence: Iterable[str]) -> tuple[int, list[str]]:
    """(how many numbers were checked, the ones no evidence supports).

    The missing list is in order of appearance and de-duplicated.
    """
    values, dates = evidence_numbers(evidence)
    missing: list[str] = []
    checked = 0

    # Dates must appear literally; year spans are context.
    for d in _DATE.findall(answer):
        checked += 1
        if d not in dates and d not in missing:
            missing.append(d)
    text = _ISO_OR_SPAN.sub(" ", answer)

    for token, v, decimals, scale in _tokens(text):
        if _exempt(v, decimals, token):
            continue
        checked += 1
        candidates = {v, v * scale} if scale != 1.0 else {v}
        ok = any(
            round(a, decimals) == round(c, decimals)
            or (scale != 1.0 and round(a / scale, decimals) == round(v, decimals))
            for a in values for c in candidates
        )
        if not ok and token not in missing:
            missing.append(token)
    return checked, missing


def unverified_numbers(answer: str, evidence: Iterable[str]) -> list[str]:
    """Numbers in `answer` that no evidence text supports."""
    return check_answer(answer, evidence)[1]


def retry_feedback(missing: list[str]) -> str:
    listed = ", ".join(missing)
    return (
        "[Automatic check, not from the user] Before an answer is shown, every number "
        "in it is checked against the tool results in this conversation and the verified "
        f"documents in your instructions. These numbers were not found in either: {listed}.\n\n"
        "Rewrite the answer so that every number is copied from a tool result — use the "
        "`display` strings exactly as the tools returned them. Don't work out differences, "
        "totals, averages, shares or rounded comparisons yourself: for warehouse numbers call "
        "compare_metric (kind 'change' or 'share') and copy its result, or say it in words "
        "without a figure (\"the highest\", \"slightly lower\"). "
        "Reply with the full corrected answer only; don't mention this check. If your "
        "answer ended with a <cannot_answer> block, keep it."
    )


# ---------------------------------------------------------------- tables

_HIDDEN_KEYS = {"source", "verified_by", "verified_on", "agent_guidance", "notes", "note",
                "quote_anchor", "caveat", "caveats", "suppressed", "display"}


def _label(key: str) -> str:
    return key.replace("_", " ").strip().capitalize() if key.islower() or "_" in key else key


def _published_cell(key: str, value: Any) -> str:
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        if key == "year" or key.endswith("_year"):
            return str(value)
        if key.endswith("_pct") or key.endswith("_percent") or key == "pct":
            return f"{value:g}%"
        return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value).replace("_", " ")


def _source_text(src: Any) -> str:
    if not isinstance(src, dict):
        return str(src or "")
    bits = [src.get("file", "")]
    if src.get("page") is not None:
        bits.append(f"p. {src['page']}")
    for k in ("figure", "table"):
        if src.get(k):
            bits.append(str(src[k]))
    return ", ".join(b for b in bits if b)


def published_table(tool_input: dict, result: dict, max_rows: int = 30) -> dict | None:
    records = [r for r in result.get("records") or [] if isinstance(r, dict)]
    if not records:
        return None
    keys: list[str] = []
    for r in records:
        for k, v in r.items():
            if k.startswith("_") or k in _HIDDEN_KEYS or isinstance(v, (dict, list)):
                continue
            if k not in keys:
                keys.append(k)
    numeric = [k for k in keys if any(isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)
                                      and k != "year" for r in records)]
    rows = [[_published_cell(k, r.get(k)) for k in keys] + [_source_text(r.get("source"))]
            for r in records[:max_rows]]
    filters = tool_input.get("filters") or {}
    return {
        "kind": "published",
        "title": _label(result.get("kpi_id") or tool_input.get("kpi_id") or "Published values"),
        "subtitle": " · ".join(f"{_label(k)} = {v}" for k, v in filters.items()),
        "columns": [{"name": _label(k), "numeric": k in numeric} for k in keys] + [{"name": "Source", "numeric": False}],
        "rows": rows,
        "notes": ([f"Showing {max_rows} of {len(records)} records."] if len(records) > max_rows else []),
    }


def warehouse_table(result: dict) -> dict | None:
    rows = result.get("rows") or []
    if not rows or "error" in result:
        return None
    by = list(result.get("by") or [])
    measures = [m["name"] for m in result.get("measures") or []]
    out_rows = []
    for r in rows:
        disp = r.get("display") or {}
        out_rows.append([str(r.get(b, "")) for b in by] + [disp.get(m, display_value(r.get(m), None)) for m in measures])
    filters = dict(result.get("filters") or {})
    defaults = result.get("applied_defaults") or {}
    sub = [f"{k} = {v}" for k, v in filters.items() if k not in defaults]
    sub += [f"{k} = {v} (default)" for k, v in defaults.items()]
    notes = []
    if result.get("suppressed_cells"):
        n = result["suppressed_cells"]
        notes.append(f"{n} cell{'s' if n != 1 else ''} suppressed: {result.get('suppression_rule', '')}.")
    if result.get("truncated"):
        notes.append(f"Showing the first {len(rows)} rows.")
    prelim = result.get("preliminary") or []
    for p in prelim:
        notes.append(f"Preliminary ({p['applies_to']}): {p['why']}")
    return {
        "kind": "synthetic",
        "title": f"{result.get('cube')} cube · {', '.join(measures)}" + (f" by {', '.join(by)}" if by else ""),
        "subtitle": " · ".join(sub),
        "columns": [{"name": b, "numeric": False} for b in by] + [{"name": m, "numeric": True} for m in measures],
        "rows": out_rows,
        "notes": notes,
        "data_as_of": result.get("data_as_of"),
        "stale": bool(result.get("stale")),
        "preliminary": bool(prelim),
        "row_preliminary": [bool(r.get("preliminary")) for r in rows] if prelim else [],
        "chart": chart_spec(result),
    }


# ---------------------------------------------------------------- charts

_YEAR = re.compile(r"(?:19|20)\d{2}")
MAX_BARS = 12


def _dim_of(column: str) -> str:
    """'1st Academic Unit.Faculty' -> '1st Academic Unit'; 'Cohort (dimension)' -> 'Cohort'."""
    return column.removesuffix(" (dimension)").split(".")[0]


def chart_spec(result: dict) -> dict | None:
    """Which chart, if any, a warehouse result gets, with the points to draw.

    Decided here from the shape of the result, never by the model:
      - funnel: the cube's funnel measures (at least three), one row;
      - line:   grouped by one time dimension, three or more distinct years;
      - bar:    grouped by one other dimension, two to twelve rows.
    One series only (the first measure). Each point carries its value (for
    geometry) and its display string (the only text drawn), so the chart shows
    exactly the numbers the table does.
    """
    rows = result.get("rows") or []
    measures = result.get("measures") or []
    if not rows or not measures or result.get("truncated") or "error" in result:
        return None
    roles = result.get("roles") or {}
    by = list(result.get("by") or [])

    def point(label: str, row: dict, name: str) -> dict:
        return {"label": label, "value": row.get(name), "display": (row.get("display") or {}).get(name, "–"),
                "preliminary": bool(row.get("preliminary"))}

    names = [m["name"] for m in measures]
    funnel = [f for f in roles.get("funnel", []) if f in names]
    if not by and len(rows) == 1 and len(funnel) >= 3:
        unit = next(m["unit"] for m in measures if m["name"] == funnel[0])
        return {"type": "funnel", "measure": "", "unit": unit,
                "points": [point(f, rows[0], f) for f in funnel]}
    if len(by) != 1:
        return None
    m, col = measures[0], by[0]
    points = [point(str(r.get(col, "")), r, m["name"]) for r in rows]
    if all(p["value"] is None for p in points):
        return None
    spec = {"measure": m["name"], "unit": m["unit"], "x": col,
            "note": f"Chart shows {m['name']}." if len(measures) > 1 else ""}
    if _dim_of(col) in roles.get("time", []):
        years = [_YEAR.search(p["label"]) for p in points]
        if len(points) >= 3 and all(years) and len({y.group(0) for y in years}) == len(points):
            points.sort(key=lambda p: _YEAR.search(p["label"]).group(0))
            return {"type": "line", **spec, "points": points}
        return None
    if 2 <= len(points) <= MAX_BARS:
        return {"type": "bar", **spec, "points": points}
    return None


# ---------------------------------------------------------------- compare

def compare_table(result: dict) -> dict | None:
    rows = result.get("rows") or []
    if not rows or "error" in result:
        return None
    by = list(result.get("by") or [])
    filters = dict(result.get("filters") or {})
    defaults = result.get("applied_defaults") or {}
    sub = [f"{k} = {v}" for k, v in filters.items() if k not in defaults]
    sub += [f"{k} = {v} (default)" for k, v in defaults.items()]
    notes = list(result.get("notes") or [])
    if result.get("not_shown"):
        notes.append(f"{result['not_shown']} not shown: a side is suppressed (small cell) or missing.")
    for p in result.get("preliminary") or []:
        notes.append(f"Preliminary ({p['applies_to']}): {p['why']}")
    measure = result.get("measure", "")
    if result.get("kind") == "change":
        along = _dim_of(str(result.get("along", "")))
        extra = ["change_pct"] if any("change_pct" in r for r in rows) else []
        cols = [*by, "from", "to", "change", *extra]
        names = [*by, f"{along} {result.get('from')}", f"{along} {result.get('to')}",
                 "Change" + (" (pp)" if result.get("unit") == "percent" else ""), *(["% change"] if extra else [])]
        title = f"{result.get('cube')} cube · change in {measure}, {result.get('from')} to {result.get('to')}"
    else:
        cols = [*by, "value", "share"]
        names = [*by, measure, "Share of total"]
        title = f"{result.get('cube')} cube · share of {measure}" + (f" by {', '.join(by)}" if by else "")
        notes.insert(0, f"Total: {result.get('total', '–')}.")
    return {
        "kind": "synthetic",
        "title": title,
        "subtitle": " · ".join(sub),
        "columns": [{"name": n, "numeric": c not in by} for c, n in zip(cols, names)],
        "rows": [[str(r.get(c, "–")) for c in cols] for r in rows],
        "notes": notes,
        "data_as_of": result.get("data_as_of"),
        "stale": bool(result.get("stale")),
        "preliminary": bool(result.get("preliminary")),
        "row_preliminary": [bool(r.get("preliminary")) for r in rows] if result.get("preliminary") else [],
        "chart": None,
    }


def model_payload(tool_name: str, result: dict) -> str:
    """What the model sees for a tool result: no SQL, and warehouse rows as
    display strings only, so there is nothing for it to reformat."""
    payload = {k: v for k, v in result.items() if k not in ("sql", "roles")}
    if tool_name == "compare_metric" and payload.get("rows"):
        payload["values_are"] = "display strings worked out by the engine: copy them exactly, without quotation marks"
    if tool_name == "query_metric" and isinstance(payload.get("rows"), list):
        measures = [m["name"] for m in payload.get("measures") or []]
        shown = []
        for r in payload["rows"]:
            disp = r.get("display") or {}
            row = {k: v for k, v in r.items() if k not in measures and k != "display"}
            row.update({m: disp.get(m) for m in measures})
            shown.append(row)
        payload["rows"] = shown
        payload["values_are"] = "display strings: copy them exactly, without quotation marks"
    if payload.get("rows") or payload.get("records"):
        # Said here, next to the numbers, because that is where the model
        # decides what to write; the instruction in the prompt alone was ignored.
        payload["shown_to_user"] = (
            "This whole result is already drawn as a table under your answer. Don't "
            "repeat it as a table or a list: name only the one to three numbers that "
            "answer the question."
        )
    return json.dumps(payload, default=str)
