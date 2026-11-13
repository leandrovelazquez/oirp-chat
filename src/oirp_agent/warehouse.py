"""
Governed metric engine over the synthetic warehouse.

The agent never writes SQL. It names a cube, measures, dimensions and filter
values; this module checks every name against the cube model declared in
`semantic_layer/warehouse/*.md` and compiles a parameterised query. Anything not
declared in the model -- a column, a table, an expression -- cannot be reached.

The cube model mirrors how the SSAS cubes are defined:

  - measure groups, each over one fact table, with base measures
    (Sum / Count / DistinctCount of a fact column)
  - calculated measures, ported from the cubes' MDX calculated members as
    ratios of base measures (numerator(s) / denominator)
  - dimensions, each joining a fact column to a dimension table's key, with an
    optional hierarchy of levels (e.g. Academic Unit -> Faculty)

On top of that, three guards that a real warehouse needs and a cube browser
does not give you:

  - required single-valued dimensions (e.g. Count Date, Years After), so that
    two counting bases are never silently summed together
  - small-cell suppression on the distinct-person count behind every cell
  - load-log freshness, so an answer can say how old its data is
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from .prompt_loader import _split_frontmatter

_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

MAX_ROWS = 300
DEFAULT_LIMIT = 100


class QueryError(ValueError):
    """A query the cube model does not allow. The message is shown to the agent."""


# ---------------------------------------------------------------------------
# Cube model
# ---------------------------------------------------------------------------


@dataclass
class Measure:
    name: str
    group: str
    kind: str                  # "base" | "calculated"
    unit: str
    description: str = ""
    agg: str | None = None     # base: sum | count | count_distinct | count_nonnull
    column: str | None = None
    numerator: list[str] = field(default_factory=list)
    denominator: str | None = None
    ssas: str | None = None    # the source cube's definition, for citation


@dataclass
class Level:
    name: str
    label: str                 # dimension-table column shown for this level
    key: str | None = None     # optional code column for filtering


@dataclass
class Dimension:
    name: str
    fact_columns: dict[str, str]          # measure group -> fact column
    table: str | None                     # None = degenerate (label is the fact value)
    key: str | None
    label: str | None
    levels: dict[str, Level] = field(default_factory=dict)
    description: str = ""


@dataclass
class MeasureGroup:
    name: str
    fact_table: str
    person_key: str
    star: str
    required: list[dict] = field(default_factory=list)   # [{dimension, default?, why}]


@dataclass
class Cube:
    cube_id: str
    name: str
    star: str
    description: str
    freshness_sla_days: int
    min_cell_size: int
    groups: dict[str, MeasureGroup]
    measures: dict[str, Measure]
    dimensions: dict[str, Dimension]
    raw_markdown: str
    source_path: Path | None = None

    def measure(self, name: str) -> Measure:
        m = _ci_get(self.measures, name)
        if m is None:
            raise QueryError(
                f"Cube '{self.name}' has no measure {name!r}. "
                f"Available: {', '.join(self.measures)}"
            )
        return m

    def dimension(self, ref: str) -> tuple[Dimension, Level | None]:
        """Resolve 'Dimension' or 'Dimension.Level'."""
        dim = _ci_get(self.dimensions, ref)
        if dim is not None:
            return dim, None
        if "." in ref:
            dname, _, lname = ref.rpartition(".")
            dim = _ci_get(self.dimensions, dname)
            if dim is not None:
                lvl = _ci_get(dim.levels, lname)
                if lvl is not None:
                    return dim, lvl
                raise QueryError(
                    f"Dimension '{dim.name}' has no level {lname!r}. "
                    f"Levels: {', '.join(dim.levels) or '(none)'}"
                )
        raise QueryError(
            f"Cube '{self.name}' has no dimension {ref!r}. "
            f"Available: {', '.join(self.dimensions)}"
        )


def _ci_get(d: dict, key: str):
    if key in d:
        return d[key]
    low = key.strip().lower()
    for k, v in d.items():
        if k.lower() == low:
            return v
    return None


def load_cube(path: Path) -> Cube:
    raw = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(raw)
    blocks = _JSON_BLOCK_RE.findall(body)
    if len(blocks) != 1:
        raise ValueError(f"{path}: expected exactly one ```json cube-model block, found {len(blocks)}")
    model = json.loads(blocks[0])

    groups: dict[str, MeasureGroup] = {}
    measures: dict[str, Measure] = {}
    for gname, g in model["measure_groups"].items():
        groups[gname] = MeasureGroup(
            name=gname, fact_table=g["fact_table"], person_key=g["person_key"],
            star=model.get("star", fm.get("star", "")), required=g.get("required_single", []),
        )
        for mname, m in g.get("measures", {}).items():
            measures[mname] = Measure(
                name=mname, group=gname, kind="base", unit=m.get("unit", "count"),
                description=m.get("description", ""), agg=m["agg"], column=m.get("column"),
                ssas=m.get("ssas"),
            )
        for mname, m in g.get("calculated", {}).items():
            measures[mname] = Measure(
                name=mname, group=gname, kind="calculated", unit=m.get("unit", "ratio"),
                description=m.get("description", ""), numerator=list(m["numerator"]),
                denominator=m["denominator"], ssas=m.get("mdx"),
            )
    # validate calculated references
    for m in measures.values():
        if m.kind == "calculated":
            for ref in m.numerator + [m.denominator]:
                if ref not in measures or measures[ref].kind != "base" or measures[ref].group != m.group:
                    raise ValueError(f"{path}: calculated measure {m.name!r} references unknown base measure {ref!r}")

    dims: dict[str, Dimension] = {}
    for dname, d in model["dimensions"].items():
        levels = {
            lname: Level(name=lname, label=lv["label"], key=lv.get("key"))
            for lname, lv in d.get("levels", {}).items()
        }
        dims[dname] = Dimension(
            name=dname, fact_columns=d["fact_columns"], table=d.get("table"),
            key=d.get("key"), label=d.get("label"), levels=levels,
            description=d.get("description", ""),
        )
    return Cube(
        cube_id=fm.get("cube_id", path.stem), name=model["cube"], star=model.get("star", ""),
        description=model.get("description", ""),
        freshness_sla_days=int(model.get("freshness_sla_days", 7)),
        min_cell_size=int(model.get("min_cell_size", 10)),
        groups=groups, measures=measures, dimensions=dims, raw_markdown=raw, source_path=path,
    )


def load_cubes(warehouse_dir: Path) -> list[Cube]:
    if not warehouse_dir.exists():
        return []
    return [load_cube(p) for p in sorted(warehouse_dir.glob("*.md"))]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _q(ident: str) -> str:
    """Quote an identifier that came from the cube model (never from the user)."""
    return '"' + ident.replace('"', '""') + '"'


def _as_list(v) -> list[str]:
    vals = v if isinstance(v, (list, tuple)) else [v]
    out = []
    for x in vals:
        if isinstance(x, float) and x.is_integer():
            x = int(x)
        out.append(str(x).strip())
    return out


class WarehouseEngine:
    def __init__(self, db_path: Path, cubes: list[Cube]) -> None:
        self.db_path = db_path
        self.cubes = {c.name: c for c in cubes}
        self._con = duckdb.connect(str(db_path), read_only=True)
        self._lock = threading.Lock()
        self._load_log = {
            r[0]: (r[1], r[2])
            for r in self._con.execute('select "TABLE_NAME", "LOADED_AT", "ROW_COUNT" from "LOAD_LOG"').fetchall()
        }
        self._newest_load = max((v[0] for v in self._load_log.values()), default=None)
        self.meta = dict(self._con.execute('select "KEY", "VALUE" from "WAREHOUSE_META"').fetchall())
        self._check_model_against_database()

    # ----- setup -----

    def _check_model_against_database(self) -> None:
        """Fail at startup, not mid-conversation, if the model names a missing column."""
        cols: dict[str, set[str]] = {}
        for t, c in self._con.execute(
            "select table_name, column_name from information_schema.columns where table_schema='main'"
        ).fetchall():
            cols.setdefault(t, set()).add(c)
        problems = []
        for cube in self.cubes.values():
            for g in cube.groups.values():
                if g.fact_table not in cols:
                    problems.append(f"{cube.name}: fact table {g.fact_table} missing")
            for m in cube.measures.values():
                if m.kind == "base" and m.column and m.column not in cols.get(cube.groups[m.group].fact_table, ()):
                    problems.append(f"{cube.name}: measure {m.name} column {m.column} missing")
            for d in cube.dimensions.values():
                for gname, fc in d.fact_columns.items():
                    if fc not in cols.get(cube.groups[gname].fact_table, ()):
                        problems.append(f"{cube.name}: dimension {d.name} fact column {fc} missing")
                if d.table:
                    needed = {d.key, d.label} | {lv.label for lv in d.levels.values()} | {
                        lv.key for lv in d.levels.values() if lv.key}
                    missing = needed - cols.get(d.table, set())
                    if missing:
                        problems.append(f"{cube.name}: dimension {d.name} table {d.table} missing {sorted(missing)}")
        if problems:
            raise RuntimeError("Cube model does not match the warehouse:\n  " + "\n  ".join(problems))

    def cube(self, name: str) -> Cube:
        c = _ci_get(self.cubes, name)
        if c is None:
            raise QueryError(f"No cube named {name!r}. Available: {', '.join(self.cubes)}")
        return c

    def _execute(self, sql: str, params: list) -> tuple[list[str], list[tuple]]:
        with self._lock:
            cur = self._con.cursor()
            try:
                res = cur.execute(sql, params)
                return [d[0] for d in res.description], res.fetchall()
            finally:
                cur.close()

    # ----- freshness -----

    def freshness(self, cube: Cube, group: MeasureGroup) -> dict:
        loaded = self._load_log.get(group.fact_table, (None, None))[0]
        if loaded is None or self._newest_load is None:
            return {"data_as_of": None, "stale": None}
        lag = (self._newest_load - loaded).days
        return {
            "data_as_of": loaded.date().isoformat(),
            "days_behind_newest_load": lag,
            "freshness_sla_days": cube.freshness_sla_days,
            "stale": lag > cube.freshness_sla_days,
        }

    # ----- describe -----

    def describe(self, cube_name: str | None = None, dimension: str | None = None) -> dict:
        if cube_name is None:
            out = []
            for c in self.cubes.values():
                g0 = next(iter(c.groups.values()))
                out.append({
                    "cube": c.name, "description": c.description,
                    "measure_groups": list(c.groups),
                    "measures": list(c.measures), "dimensions": list(c.dimensions),
                    **self.freshness(c, g0),
                })
            return {"data_origin": self.meta.get("data_origin"), "cubes": out}

        cube = self.cube(cube_name)
        if dimension is None:
            return {
                "cube": cube.name,
                "data_origin": self.meta.get("data_origin"),
                "measure_groups": {
                    g.name: {
                        "fact_table": g.fact_table,
                        "required_single_dimensions": g.required,
                        **self.freshness(cube, g),
                    } for g in cube.groups.values()
                },
                "measures": [
                    {"name": m.name, "group": m.group, "unit": m.unit, "kind": m.kind,
                     "description": m.description, "source_definition": m.ssas}
                    for m in cube.measures.values()
                ],
                "dimensions": [
                    {"name": d.name, "levels": list(d.levels), "measure_groups": list(d.fact_columns),
                     "description": d.description}
                    for d in cube.dimensions.values()
                ],
                "min_cell_size": cube.min_cell_size,
            }

        dim, level = cube.dimension(dimension)
        if dim.table:
            cols = [dim.key, dim.label] + [c for lv in dim.levels.values() for c in (lv.key, lv.label) if c]
            cols = list(dict.fromkeys(cols))
            names, rows = self._execute(
                f"select distinct {', '.join(_q(c) for c in cols)} from {_q(dim.table)} order by 1 limit 400", [])
            members = [dict(zip(names, r)) for r in rows]
        else:
            gname, fc = next(iter(dim.fact_columns.items()))
            names, rows = self._execute(
                f"select distinct cast({_q(fc)} as varchar) as value from "
                f"{_q(cube.groups[gname].fact_table)} order by 1 limit 400", [])
            members = [{"value": r[0]} for r in rows]
        return {
            "cube": cube.name, "dimension": dim.name, "levels": list(dim.levels),
            "description": dim.description, "member_count": len(members), "members": members,
            "how_to_filter": "Filter values may be a member key or its label (case-insensitive); "
                             "use 'Dimension.Level' to filter or group at a level.",
        }

    # ----- query -----

    def query(
        self,
        cube_name: str,
        measures: list[str],
        by: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> dict:
        cube = self.cube(cube_name)
        by = list(by or [])
        filters = dict(filters or {})
        limit = min(int(limit or DEFAULT_LIMIT), MAX_ROWS)
        if not measures:
            raise QueryError("Name at least one measure.")

        ms = [cube.measure(m) for m in measures]
        groups = {m.group for m in ms}
        if len(groups) > 1:
            raise QueryError(
                f"Measures {', '.join(m.name for m in ms)} come from different measure groups "
                f"({', '.join(sorted(groups))}); query them separately."
            )
        group = cube.groups[groups.pop()]
        fact = group.fact_table

        base_needed: list[Measure] = []
        for m in ms:
            refs = [m] if m.kind == "base" else [cube.measures[r] for r in m.numerator + [m.denominator]]
            for b in refs:
                if b not in base_needed:
                    base_needed.append(b)

        # Resolve dimension references (group-bys and filters).
        joins: dict[str, str] = {}   # dim name -> alias

        def resolve(ref: str) -> tuple[Dimension, Level | None, str]:
            dim, lvl = cube.dimension(ref)
            if group.name not in dim.fact_columns:
                raise QueryError(
                    f"Dimension '{dim.name}' is not related to measure group '{group.name}' "
                    f"(it applies to: {', '.join(dim.fact_columns)})."
                )
            if dim.table and dim.name not in joins:
                joins[dim.name] = f"d{len(joins)}"
            return dim, lvl, joins.get(dim.name, "")

        group_exprs: list[tuple[str, str]] = []   # (output name, sql)
        for ref in by:
            dim, lvl, alias = resolve(ref)
            fc = f"f.{_q(dim.fact_columns[group.name])}"
            if lvl is not None:
                expr = f"coalesce(cast({alias}.{_q(lvl.label)} as varchar), '(Unknown)')"
                out = f"{dim.name}.{lvl.name}"
            elif dim.table:
                expr = f"coalesce(cast({alias}.{_q(dim.label)} as varchar), '(Unknown)')"
                out = dim.name
            else:
                expr = f"coalesce(cast({fc} as varchar), '(Unknown)')"
                out = dim.name
            # e.g. Retention's `Cohort` is both a dimension and a measure.
            if any(out.lower() == m.name.lower() for m in ms):
                out = f"{out} (dimension)"
            group_exprs.append((out, expr))

        applied_defaults: dict[str, str] = {}
        grouped_dims = {cube.dimension(r)[0].name for r in by}
        filtered_single: set[str] = set()
        for ref, v in filters.items():
            dim, lvl, _ = resolve(ref)
            if lvl is None and len(_as_list(v)) == 1:
                filtered_single.add(dim.name)
        for req in group.required:
            dname = req["dimension"]
            if dname in grouped_dims or dname in filtered_single:
                continue
            if req.get("default") is not None and not any(
                    cube.dimension(r)[0].name == dname for r in filters):
                filters[dname] = req["default"]
                applied_defaults[dname] = str(req["default"])
                filtered_single.add(dname)

        where: list[str] = []
        params: list[Any] = []
        for ref, v in filters.items():
            dim, lvl, alias = resolve(ref)
            vals = [x.lower() for x in _as_list(v)]
            ph = ", ".join("?" for _ in vals)
            fc = f"f.{_q(dim.fact_columns[group.name])}"
            if lvl is not None:
                cond = f"lower(cast({alias}.{_q(lvl.label)} as varchar)) in ({ph})"
                params += vals
                if lvl.key:
                    cond = f"({cond} or lower(cast({alias}.{_q(lvl.key)} as varchar)) in ({ph}))"
                    params += vals
            elif dim.table:
                cond = (f"(lower(cast({fc} as varchar)) in ({ph}) or "
                        f"lower(cast({alias}.{_q(dim.label)} as varchar)) in ({ph}))")
                params += vals + vals
            else:
                cond = f"lower(cast({fc} as varchar)) in ({ph})"
                params += vals
            where.append(cond)

        join_sql = ""
        for dname, alias in joins.items():
            dim = cube.dimensions[dname]
            join_sql += (f" left join {_q(dim.table)} {alias} on cast(f.{_q(dim.fact_columns[group.name])} "
                         f"as varchar) = cast({alias}.{_q(dim.key)} as varchar)")
        where_sql = (" where " + " and ".join(where)) if where else ""
        from_sql = f" from {_q(fact)} f{join_sql}{where_sql}"

        # Required single-valued dimensions: measure, don't assume.
        for req in group.required:
            dname = req["dimension"]
            if dname in grouped_dims or dname in filtered_single:
                continue
            dim = cube.dimensions[dname]
            fc = f"f.{_q(dim.fact_columns[group.name])}"
            _, rows = self._execute(
                f"select distinct cast({fc} as varchar){from_sql} order by 1 limit 40", params)
            if len(rows) > 1:
                raise QueryError(
                    f"'{dname}' must be filtered to ONE value or included in `by` -- {req.get('why', '')} "
                    f"Values present under your filters: {', '.join(r[0] for r in rows if r[0] is not None)}"
                )

        select_parts = [f"{expr} as {_q(out)}" for out, expr in group_exprs]
        for b in base_needed:
            col = f"f.{_q(b.column)}" if b.column else None
            sql = {"sum": f"sum({col})", "count": "count(*)",
                   "count_distinct": f"count(distinct {col})",
                   "count_nonnull": f"count({col})"}[b.agg]
            select_parts.append(f"{sql} as {_q('__' + b.name)}")
        select_parts.append(f"count(distinct f.{_q(group.person_key)}) as \"__n\"")
        group_sql = (" group by " + ", ".join(str(i + 1) for i in range(len(group_exprs)))) if group_exprs else ""
        sql = f"select {', '.join(select_parts)}{from_sql}{group_sql}"
        names, rows = self._execute(sql, params)
        if len(rows) > MAX_ROWS:
            raise QueryError(f"{len(rows)} result rows; narrow the filters or group by fewer dimensions.")

        out_rows = []
        suppressed = 0
        for r in rows:
            rec = dict(zip(names, r))
            n = rec.pop("__n") or 0
            base_vals = {b.name: rec.pop("__" + b.name) for b in base_needed}
            row = {k: v for k, v in rec.items()}
            if n == 0 and all(v in (None, 0) for v in base_vals.values()):
                continue
            if 0 < n < cube.min_cell_size:
                for m in ms:
                    row[m.name] = None
                row["suppressed"] = True
                suppressed += 1
            else:
                for m in ms:
                    row[m.name] = _value(m, base_vals, cube)
            out_rows.append(row)

        if order_by:
            key = next((k for k in (out_rows[0].keys() if out_rows else []) if k.lower() == order_by.lower()), None)
            if key is None:
                raise QueryError(f"order_by {order_by!r} is not a measure or `by` column in this query.")
            out_rows.sort(key=lambda r: (r[key] is None, r[key]), reverse=descending)
        else:
            out_rows.sort(key=lambda r: tuple(str(r[o]) for o, _ in group_exprs))
        truncated = len(out_rows) > limit
        out_rows = out_rows[:limit]

        return {
            "data_origin": "SYNTHETIC -- generated demo data, not real institutional figures",
            "cube": cube.name,
            "measure_group": group.name,
            "fact_table": fact,
            "measures": [{"name": m.name, "unit": m.unit, "source_definition": m.ssas} for m in ms],
            "by": [o for o, _ in group_exprs],
            "filters": {k: v for k, v in filters.items()},
            "applied_defaults": applied_defaults,
            "row_count": len(out_rows),
            "truncated": truncated,
            "rows": out_rows,
            "suppressed_cells": suppressed,
            "suppression_rule": f"cells with fewer than {cube.min_cell_size} distinct people are suppressed",
            **self.freshness(cube, group),
            "sql": sql,
        }


def _value(m: Measure, base: dict, cube: Cube):
    if m.kind == "base":
        v = base[m.name]
    else:
        num = sum((base[n] or 0) for n in m.numerator)
        den = base[m.denominator]
        v = (num / den) if den else None
    if v is None:
        return None
    if m.unit == "percent":
        return round(100.0 * v, 1)
    if m.unit in ("students", "applicants", "people", "rows"):
        return round(v) if abs(v - round(v)) < 1e-6 else round(v, 1)
    if m.unit == "gpa_12pt":
        return round(v, 2)
    return round(v, 1)
