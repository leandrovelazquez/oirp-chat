"""
compare_metric (the engine's arithmetic), charts drawn from result rows, and
follow-up questions worked out from the query. None of these involve the model.
"""

from __future__ import annotations

import json

import pytest

from oirp_agent.followups import follow_ups, previous
from oirp_agent.numbers import chart_spec, check_answer, compare_table, model_payload
from oirp_agent.tools import ToolDispatcher
from oirp_agent.warehouse import QueryError

from test_numbers import RETENTION_BY_FACULTY, _agent, _retention, _text, _tool, layer  # noqa: F401

FUNNEL = ["Applicants", "Approved", "Confirmed", "Registered"]


def _value(engine, cube, measure, **filters):
    return engine.query(cube, [measure], filters=filters)["rows"][0][measure]


# ---- compare_metric ---------------------------------------------------------


def test_change_in_a_rate_is_in_points_and_matches_the_two_queries(engine):
    r = engine.compare("Retention", "% Continuing", "change", along="Cohort", from_value=2023, to_value=2024,
                       by=["1st Academic Unit.Faculty"], filters={"Years After": 1})
    fed = next(row for row in r["rows"] if row["1st Academic Unit.Faculty"] == "Faculty of Engineering and Design")
    a = engine.query("Retention", ["% Continuing"], filters={"Cohort": 2023, "Years After": 1,
                                                            "1st Academic Unit.Faculty": "Faculty of Engineering and Design"})
    b = engine.query("Retention", ["% Continuing"], filters={"Cohort": 2024, "Years After": 1,
                                                            "1st Academic Unit.Faculty": "Faculty of Engineering and Design"})
    va, vb = a["rows"][0]["% Continuing"], b["rows"][0]["% Continuing"]
    assert fed["from"] == a["rows"][0]["display"]["% Continuing"]
    assert fed["to"] == b["rows"][0]["display"]["% Continuing"]
    sign = "+" if vb > va else "−"
    assert fed["change"] == f"{sign}{abs(vb - va):.1f} pp"
    assert "change_pct" not in fed           # no percent change of a rate


def test_change_in_a_count_has_a_percent_change_and_carries_preliminary(engine):
    r = engine.compare("Enrolment", "Student Count", "change", along="Time", from_value="Fall 2025",
                       to_value="Fall 2026", filters={"Student Level": "Undergraduate"})
    row = r["rows"][0]
    va = _value(engine, "Enrolment", "Student Count", Time="Fall 2025", **{"Student Level": "Undergraduate"})
    vb = _value(engine, "Enrolment", "Student Count", Time="Fall 2026", **{"Student Level": "Undergraduate"})
    assert row["change"].lstrip("+−").replace(",", "") == str(abs(vb - va))
    assert row["change_pct"].endswith("%") and row["preliminary"] is True
    assert r["preliminary"][0]["applies_to"] == "Time = Fall 2026"


def test_share_uses_the_true_total(engine):
    r = engine.compare("Enrolment", "Student Count", "share", by=["Tuition Assessment"],
                       filters={"Time": "Fall 2025", "Student Level": "Undergraduate"})
    total = _value(engine, "Enrolment", "Student Count", Time="Fall 2025", **{"Student Level": "Undergraduate"})
    intl = next(row for row in r["rows"] if row["Tuition Assessment"] == "International")
    count = int(intl["value"].replace(",", ""))
    assert intl["share"] == f"{100 * count / total:.1f}%"
    assert r["total"] == f"{total:,}"


def test_share_of_a_rate_and_a_change_without_ends_are_refused(engine):
    with pytest.raises(QueryError, match="count measure"):
        engine.compare("Retention", "% Continuing", "share", by=["Cohort"], filters={"Years After": 1})
    with pytest.raises(QueryError, match="along"):
        engine.compare("Retention", "% Continuing", "change", filters={"Years After": 1})


def test_the_model_can_copy_a_change_and_pass_the_number_check(engine):
    r = ToolDispatcher(None, engine).dispatch("compare_metric", {
        "cube": "Retention", "measure": "% Continuing", "kind": "change", "along": "Cohort",
        "from": 2023, "to": 2024, "filters": {"Years After": 1}})
    payload = model_payload("compare_metric", r)
    assert "sql" not in json.loads(payload) and "values_are" in json.loads(payload)
    change = r["rows"][0]["change"]
    assert check_answer(f"Retention moved by {change} (synthetic).", [payload])[1] == []


def test_compare_is_drawn_as_a_table(engine):
    r = engine.compare("Retention", "% Continuing", "change", along="Cohort", from_value=2023, to_value=2024,
                       filters={"Years After": 1})
    t = compare_table(r)
    assert [c["name"] for c in t["columns"]] == ["Cohort 2023", "Cohort 2024", "Change (pp)"]
    assert t["rows"][0][2] == r["rows"][0]["change"]


def test_agent_records_compare_as_a_synthetic_high_confidence_lookup(layer):
    agent = _agent(layer, [
        _tool("compare_metric", {"cube": "Retention", "measure": "% Continuing", "kind": "change",
                                 "along": "Cohort", "from": 2023, "to": 2024, "filters": {"Years After": 1}}),
        _text("Done."),
    ])
    result = agent.chat("How did retention change from 2023 to 2024?")
    assert result.confidence.value == "high" and result.trace.sources == ["synthetic"]
    assert result.tables and result.tables[0]["title"].startswith("Retention cube · change")


# ---- charts -----------------------------------------------------------------


def test_breakdown_is_a_bar_chart_of_display_strings(engine):
    r = _retention(engine)
    c = chart_spec(r)
    assert c["type"] == "bar" and len(c["points"]) == len(r["rows"])
    assert [p["display"] for p in c["points"]] == [row["display"]["% Continuing"] for row in r["rows"]]


def test_trend_is_a_line_in_year_order_with_the_preliminary_point_marked(engine):
    r = engine.query("Enrolment", ["Student Count"], by=["Time"], filters={"Time.Semester": "Fall"})
    c = chart_spec(r)
    assert c["type"] == "line"
    labels = [p["label"] for p in c["points"]]
    assert labels == sorted(labels, key=lambda s: s[-4:]) and labels[-1] == "Fall 2026"
    assert [p["preliminary"] for p in c["points"]].count(True) == 1


def test_mixed_terms_and_single_numbers_get_no_chart(engine):
    assert chart_spec(engine.query("Enrolment", ["Student Count"], by=["Time"])) is None   # fall and winter
    assert chart_spec(engine.query("Retention", ["% Continuing"], filters={"Cohort": 2024, "Years After": 1})) is None


def test_admissions_funnel_is_in_funnel_order(engine):
    r = engine.query("Admissions", list(reversed(FUNNEL)), filters={"Application Year": 2025})
    c = chart_spec(r)
    assert c["type"] == "funnel" and [p["label"] for p in c["points"]] == FUNNEL


# ---- follow-ups -------------------------------------------------------------


def test_previous_period():
    assert previous("Fall 2025") == "Fall 2024"
    assert previous(2024) == "2023"
    assert previous("2025/26") == "2024/25"
    assert previous("202530") is None          # a term code, not a label: no guess


def test_follow_ups_come_from_the_query_shape(engine):
    single = engine.query("Retention", ["% Continuing"], filters={"Cohort": 2024, "Years After": 1})
    assert follow_ups(single) == ["Break this down by faculty.", "Same for the 2023 cohort.",
                                  "Show the trend over the last five cohorts."]
    by_faculty = follow_ups(_retention(engine))
    assert "Break this down by faculty." not in by_faculty and "Same for the 2023 cohort." in by_faculty
    trend = follow_ups(engine.query("Retention", ["% Continuing"], by=["Cohort"], filters={"Years After": 1}))
    assert trend == ["Break this down by faculty."]
    enrol = follow_ups(engine.query("Enrolment", ["Student Count"], filters={"Time": "Fall 2025"}))
    assert "Same for Fall 2024." in enrol


def test_follow_ups_reach_the_answer_but_not_a_cant_answer(layer):
    answered = _agent(layer, [_tool("query_metric", RETENTION_BY_FACULTY), _text("Shown below (synthetic).")])
    assert "Same for the 2023 cohort." in answered.chat("Retention by faculty, 2024 cohort?").follow_ups
    refused = _agent(layer, [_tool("query_metric", RETENTION_BY_FACULTY), _text(
        'No.\n<cannot_answer reason="person"><ask>Q?</ask></cannot_answer>')])
    assert refused.chat("Retention by faculty, 2024 cohort?").follow_ups == []


def test_roles_are_not_sent_to_the_model(engine):
    assert "roles" not in json.loads(model_payload("query_metric", _retention(engine)))
