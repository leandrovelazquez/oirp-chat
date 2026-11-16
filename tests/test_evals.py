"""
The eval suite's own checks, without calling the model: the question file is
valid and every expected query runs, and the row comparison accepts an
equivalent query but not a different one.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from oirp_agent.confidence import ConfidenceTier, TurnTrace
from oirp_agent.evals import check_definitions, cost_usd, load_questions, rows_match, score
from oirp_agent.kpi_store import KPIStore
from oirp_agent.prompt_loader import load_semantic_layer

SL = Path(__file__).resolve().parents[1] / "semantic_layer"
SPEC = {"cube": "Retention", "measures": ["% Continuing"], "by": ["1st Academic Unit.Faculty"],
        "filters": {"Cohort": 2024, "Years After": 1}}


def test_question_file_is_valid_and_every_expected_query_runs(engine):
    store = KPIStore(load_semantic_layer(SL / "kpis"))
    assert check_definitions(load_questions(), engine, store) == []


def test_equivalent_query_matches(engine):
    same = {**SPEC, "measures": ["% continuing", "Cohort"],           # extra measure, other case
            "filters": {"Cohort": "2024", "Years After": "1"}}          # strings instead of ints
    assert rows_match(engine, SPEC, [same])[0]


def test_different_query_does_not_match(engine):
    other = {**SPEC, "filters": {"Cohort": 2023, "Years After": 1}}
    ok, why = rows_match(engine, SPEC, [other])
    assert not ok and "expected" in why
    assert not rows_match(engine, SPEC, [])[0]


def _result(text, calls=(), confidence=ConfidenceTier.HIGH, tables=(), unverified=()):
    trace = TurnTrace()
    trace.calls.extend(calls)
    return SimpleNamespace(text=text, trace=trace, confidence=confidence, tables=list(tables),
                           unverified=list(unverified))


def test_key_facts_count_the_tables_and_ignore_case_dashes_and_underscores():
    q = {"expected_key_facts": ["0-60", "overall experience", ["CUDO", "Departmental Measures"], "84.1%"]}
    table = {"title": "t", "columns": [{"name": "% Continuing"}], "rows": [["84.1%"]]}
    checks = score(q, _result("Scores run 0–60. See Overall_Experience and the departmental measures.",
                              tables=[table]), None)
    assert checks["facts"][0], checks


def test_unverified_numbers_fail_every_question():
    checks = score({}, _result("It was 99.9%.", unverified=["99.9%"]), None)
    assert checks["numbers"] == (False, "not from any tool: 99.9%")


def test_cost_estimate():
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 1_000_000}
    assert round(cost_usd("claude-sonnet-4-6", usage), 2) == 3.00 + 1.50 + 0.30
    assert cost_usd("some-unknown-model", usage) is None
