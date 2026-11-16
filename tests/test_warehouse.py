"""
Tests for the synthetic warehouse and the governed metric engine.

These pin down the guarantees the agent relies on: names are validated, counting
rules are enforced, small cells are suppressed, and the three cubes agree with
each other because they are generated from one population.

Run:  python -m pytest tests -q
(The first run builds data/warehouse/cudw_synthetic.duckdb, ~1 minute.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oirp_agent.confidence import ConfidenceTier, TurnTrace
from oirp_agent.prompt_loader import assemble_system_prompt, load_semantic_layer
from oirp_agent.tools import ToolDispatcher
from oirp_agent.kpi_store import KPIStore
from oirp_agent.warehouse import QueryError, load_cubes

ROOT = Path(__file__).resolve().parents[1]
SL = ROOT / "semantic_layer"
# The `engine` fixture lives in conftest.py.


def one(result: dict, measure: str):
    assert result["row_count"] == 1, result
    return result["rows"][0][measure]


# ---- model / names --------------------------------------------------------


def test_cube_models_load_and_match_database(engine):
    # WarehouseEngine.__init__ raises if any model column is missing.
    assert set(engine.cubes) == {"Retention", "Enrolment", "Admissions"}


def test_unknown_measure_lists_alternatives(engine):
    with pytest.raises(QueryError, match="Available"):
        engine.query("Retention", ["Retention Rate"], filters={"Years After": 1})


def test_names_are_case_insensitive(engine):
    r = engine.query("retention", ["% continuing"], filters={"cohort": 2022, "years after": 1})
    assert 50 < one(r, "% Continuing") < 100


def test_measures_from_two_groups_are_refused(engine):
    with pytest.raises(QueryError, match="different measure groups"):
        engine.query("Enrolment", ["Student Count", "Acadunit Weighted Count"], filters={"Time": "Fall 2025"})


def test_dimension_not_in_measure_group_is_refused(engine):
    with pytest.raises(QueryError, match="not related"):
        engine.query("Enrolment", ["Student Count"], by=["Academic Unit"], filters={"Time": "Fall 2025"})


def test_dimension_and_measure_with_same_name_do_not_collide(engine):
    # `Cohort` is both a dimension and a measure in the Retention cube.
    r = engine.query("Retention", ["Cohort"], by=["Cohort"], filters={"Years After": 1})
    first = r["rows"][0]
    assert first["Cohort (dimension)"] == "2011"
    assert first["Cohort"] > 1000


def test_filter_values_are_parameters_not_sql(engine):
    r = engine.query("Retention", ["Cohort"], filters={"Years After": 1, "Cohort": "2022' or '1'='1"})
    assert r["row_count"] == 0


# ---- counting rules -------------------------------------------------------


def test_retention_requires_years_after(engine):
    with pytest.raises(QueryError, match="Years After"):
        engine.query("Retention", ["% Continuing"], filters={"Cohort": 2022})


def test_year_zero_is_everyone_continuing(engine):
    r = engine.query("Retention", ["% Continuing", "% Graduating"], filters={"Cohort": 2024, "Years After": 0})
    assert one(r, "% Continuing") == 100.0
    assert one(r, "% Graduating") == 0.0


def test_enrolment_defaults_to_official_count(engine):
    r = engine.query("Enrolment", ["Student Count"], filters={"Time": "Fall 2025"})
    assert r["applied_defaults"] == {"Count Date": "P"}


def test_enrolment_refuses_to_span_terms(engine):
    with pytest.raises(QueryError, match="Time"):
        engine.query("Enrolment", ["Student Count"], filters={"Time.Academic Year": "2025/26"})


def test_enrolment_grouped_by_term_is_allowed(engine):
    r = engine.query("Enrolment", ["Student Count"], by=["Time"], filters={"Time.Semester": "Fall"})
    assert r["row_count"] == 11  # Fall 2016 .. Fall 2026


def test_term_accepts_code_or_label(engine):
    a = engine.query("Enrolment", ["Student Count"], filters={"Time": "202530"})
    b = engine.query("Enrolment", ["Student Count"], filters={"Time": "fall 2025"})
    assert one(a, "Student Count") == one(b, "Student Count")


def test_count_dates_are_ordered(engine):
    r = engine.query("Enrolment", ["Student Count"], by=["Count Date"], filters={"Time": "Fall 2025"})
    by_cnt = {row["Count Date"]: row["Student Count"] for row in r["rows"]}
    assert by_cnt["Initial count"] > by_cnt["Official count (snapshot date)"] > by_cnt["Final count"]


def test_current_term_has_no_final_count(engine):
    r = engine.query("Enrolment", ["Student Count"], filters={"Time": "Fall 2026", "Count Date": "F"})
    assert r["row_count"] == 0


# ---- suppression / freshness ---------------------------------------------


def test_small_cells_are_suppressed(engine):
    r = engine.query("Retention", ["% Continuing"], by=["1st Academic Unit", "Region"],
                     filters={"Cohort": 2025, "Years After": 1, "Region.Category": "International"})
    assert r["suppressed_cells"] > 0
    assert all(row["% Continuing"] is None for row in r["rows"] if row.get("suppressed"))


def test_retention_star_is_flagged_stale(engine):
    r = engine.query("Retention", ["Cohort"], filters={"Years After": 0, "Cohort": 2026})
    assert r["stale"] is True and r["days_behind_newest_load"] >= 21
    e = engine.query("Enrolment", ["Student Count"], filters={"Time": "Fall 2026"})
    assert e["stale"] is False


# ---- cross-cube consistency (one simulated population) ---------------------


def test_registered_equals_cohort_equals_new_undergrads(engine):
    reg = one(engine.query("Admissions", ["Registered"], filters={"Application Year": 2024}), "Registered")
    coh = one(engine.query("Retention", ["Cohort"], filters={"Cohort": 2024, "Years After": 0}), "Cohort")
    new = one(engine.query("Enrolment", ["Student Count"], filters={
        "Time": "Fall 2024", "Student Level": "Undergraduate", "New - Returning": "New"}), "Student Count")
    assert reg == coh == new


def test_faculty_weighted_counts_sum_to_headcount(engine):
    fac = engine.query("Enrolment", ["Acadunit Weighted Count"], by=["Academic Unit.Faculty"],
                       filters={"Time": "Fall 2025"})
    total = sum(r["Acadunit Weighted Count"] for r in fac["rows"])
    hc = one(engine.query("Enrolment", ["Student Count"], filters={"Time": "Fall 2025"}), "Student Count")
    assert abs(total - hc) < 1


def test_calculated_measure_matches_its_mdx(engine):
    r = engine.query("Admissions", ["Registered", "Confirmed", "% Registered of Confirmed"],
                     filters={"Application Year": 2023})
    row = r["rows"][0]
    assert row["% Registered of Confirmed"] == round(100 * row["Registered"] / row["Confirmed"], 1)


# ---- integration with tools / confidence / prompt -------------------------


def test_dispatcher_returns_errors_not_exceptions(engine):
    store = KPIStore(load_semantic_layer(SL / "kpis"))
    d = ToolDispatcher(store, engine)
    out = d.dispatch("query_metric", {"cube": "Retention", "measures": ["% Continuing"]})
    assert "error" in out and "Years After" in out["error"]


def test_confidence_high_for_metric_hit_low_for_miss(engine):
    store = KPIStore(load_semantic_layer(SL / "kpis"))
    d = ToolDispatcher(store, engine)
    hit = {"cube": "Retention", "measures": ["% Continuing"], "filters": {"Cohort": 2022, "Years After": 1}}
    miss = {"cube": "Retention", "measures": ["% Continuing"], "filters": {"Cohort": 1999, "Years After": 1}}

    t = TurnTrace()
    t.record_query_metric(hit, d.dispatch("query_metric", hit))
    assert t.confidence is ConfidenceTier.HIGH and t.sources == ["synthetic"]

    t = TurnTrace()
    t.record_query_metric(miss, d.dispatch("query_metric", miss))
    assert t.confidence is ConfidenceTier.LOW and t.sources == []


def test_system_prompt_includes_both_layers():
    docs = load_semantic_layer(SL / "kpis")
    cubes = load_cubes(SL / "warehouse")
    prompt = assemble_system_prompt(SL / "base_prompt.md", docs, [(c.name, c.raw_markdown) for c in cubes])
    assert "{{" not in prompt
    assert "## Cube: `Retention` (SYNTHETIC)" in prompt
    assert "## KPI: `overall_experience_rating`" in prompt
