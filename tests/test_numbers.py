"""
Tests for numbers.py and the agent's number check: "the model never supplies a
number" is enforced, the tools format their own numbers, and the page's tables
come from tool results.

No test calls the Anthropic API: the agent loop runs against a scripted fake
client.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from oirp_agent.agent import OIRPAgent, SemanticLayer
from oirp_agent.kpi_store import KPIStore
from oirp_agent.numbers import (
    check_answer,
    display_value,
    model_payload,
    published_table,
    warehouse_table,
)
from oirp_agent.prompt_loader import load_semantic_layer
from oirp_agent.tools import ToolDispatcher

SL = Path(__file__).resolve().parents[1] / "semantic_layer"

RETENTION_BY_FACULTY = {
    "cube": "Retention",
    "measures": ["% Continuing"],
    "by": ["1st Academic Unit.Faculty"],
    "filters": {"Cohort": 2024, "Years After": 1},
}


def _retention(engine):
    q = RETENTION_BY_FACULTY
    return engine.query(q["cube"], q["measures"], by=q["by"], filters=q["filters"])


# ---- display strings ------------------------------------------------------


def test_display_strings():
    assert display_value(90.66, "percent") == "90.7%"
    assert display_value(1513, "students") == "1,513"
    assert display_value(1234.5, "students") == "1,234.5"
    assert display_value(7.416, "gpa_12pt") == "7.42"
    assert display_value(None, "percent") == "–"
    assert display_value(None, "percent", suppressed=True, threshold=10) == "fewer than 10"


def test_warehouse_rows_carry_display_strings(engine):
    r = _retention(engine)
    for row in r["rows"]:
        assert row["display"]["% Continuing"] == f"{row['% Continuing']:.1f}%"


def test_suppressed_cells_display_as_fewer_than_threshold(engine):
    r = engine.query("Retention", ["% Continuing"], by=["1st Academic Unit", "Region"],
                     filters={"Cohort": 2025, "Years After": 1, "Region.Category": "International"})
    hidden = [row for row in r["rows"] if row.get("suppressed")]
    assert hidden, "expected at least one suppressed department"
    assert all(row["display"]["% Continuing"] == "fewer than 10" for row in hidden)


def test_model_sees_display_strings_only_and_no_sql(engine):
    d = ToolDispatcher(KPIStore([]), engine)
    payload = json.loads(model_payload("query_metric", d.dispatch("query_metric", RETENTION_BY_FACULTY)))
    assert "sql" not in payload
    for row in payload["rows"]:
        assert isinstance(row["% Continuing"], str) and row["% Continuing"].endswith("%")
        assert "display" not in row


# ---- the check ------------------------------------------------------------


EVIDENCE = ['{"rows": [{"Faculty": "FED", "% Continuing": "90.7%", "Cohort": "1,513"},'
            ' {"Faculty": "FASS", "% Continuing": "84.1%"}], "data_as_of": "2026-10-22", "share": 0.27}']


def test_numbers_copied_from_tools_pass():
    checked, missing = check_answer("FED retained 90.7% of 1,513 students (as of 2026-10-22).", EVIDENCE)
    assert missing == [] and checked == 3


def test_rounding_a_tool_number_passes():
    assert check_answer("About 91% stayed.", EVIDENCE)[1] == []


def test_fraction_supports_a_percentage():
    assert check_answer("27% took part.", EVIDENCE)[1] == []


def test_a_number_the_model_worked_out_fails():
    checked, missing = check_answer("FED leads FASS by 6.6 pp, and 2,030 people answered.", EVIDENCE)
    assert missing == ["6.6 pp", "2,030"]


def test_a_date_must_appear_literally():
    assert check_answer("As of 2026-11-01.", EVIDENCE)[1] == ["2026-11-01"]


def test_context_numbers_are_not_checked():
    text = ("In 2024, the 3 largest faculties, Years After 1, in 2024-25 and 2024/25, the 1st year, "
            "Q3, see `nsse_2023_summary.pdf`, p. 5, Table 3.")
    assert check_answer(text, []) == (0, [])


def test_a_scale_range_from_zero_is_context_but_a_percentage_range_is_not():
    assert check_answer("Each indicator is scored on a 0–60 scale (0 to 100 for some).", []) == (0, [])
    assert check_answer("Scores ran 0–60% higher.", [])[1] == ["60%"]
    assert check_answer("A share of 10–60 students.", [])[1] == ["60"]   # not from zero: checked


# ---- tables ---------------------------------------------------------------


def test_warehouse_table_is_drawn_from_display_strings(engine):
    r = _retention(engine)
    t = warehouse_table(r)
    assert t["kind"] == "synthetic"
    assert [c["name"] for c in t["columns"]] == ["1st Academic Unit.Faculty", "% Continuing"]
    assert [row[1] for row in t["rows"]] == [row["display"]["% Continuing"] for row in r["rows"]]
    assert t["stale"] is True and t["data_as_of"]


def test_published_table_shows_value_and_source():
    store = KPIStore(load_semantic_layer(SL / "kpis"))
    d = ToolDispatcher(store)
    inp = {"kpi_id": "overall_experience_rating", "filters": {"year": 2023, "cohort": "first_year"}}
    t = published_table(inp, d.dispatch("get_kpi_value", inp))
    assert t["kind"] == "published"
    flat = [c for row in t["rows"] for c in row]
    assert "74%" in flat
    assert any(c.startswith("nsse_2023_summary.pdf, p. 5") for c in flat)


# ---- the agent loop, with a scripted model --------------------------------


def _text(t):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=t)], stop_reason="end_turn")


def _tool(name, inp, id_="tu_1"):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)],
                           stop_reason="tool_use")


class FakeClient:
    """Stands in for anthropic.Anthropic: returns scripted responses in order."""

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[list[dict]] = []
        self.messages = self

    def create(self, **kw):
        self.requests.append(json.loads(json.dumps(kw["messages"], default=str)))
        return self.script.pop(0)


@pytest.fixture(scope="module")
def layer(engine):
    return SemanticLayer.load(SL / "kpis", SL / "base_prompt.md")


def _agent(layer, script):
    return OIRPAgent(SL / "kpis", SL / "base_prompt.md", layer=layer, client=FakeClient(script))


def _top_rate(engine):
    rows = _retention(engine)["rows"]
    return max(rows, key=lambda r: r["% Continuing"])["display"]["% Continuing"]


def test_unsupported_number_gets_one_rewrite_and_history_stays_clean(layer, engine):
    top = _top_rate(engine)
    agent = _agent(layer, [
        _tool("query_metric", RETENTION_BY_FACULTY),
        _text(f"The highest is {top}, ahead of the lowest by 4.21 points."),
        _text(f"In the synthetic warehouse the highest is {top}."),
    ])
    result = agent.chat("What was first-year retention by faculty for the 2024 cohort?")

    assert result.unverified == [] and result.number_retries == 1 and result.numbers_checked == 1
    assert result.text.endswith(f"{top}.")
    # The rewrite request named the bad number...
    feedback = agent.client.requests[-1][-1]["content"]
    assert "4.21" in feedback and "Automatic check" in feedback
    # ...and neither it nor the failed answer is left in history.
    flat = json.dumps(agent.history)
    assert "Automatic check" not in flat and "4.21" not in flat
    roles = [m["role"] for m in agent.history]
    assert all(a != b for a, b in zip(roles, roles[1:])), roles
    # The page gets the numbers from the tool, not the text.
    assert result.tables and result.tables[0]["kind"] == "synthetic"


def test_answer_still_unsupported_after_rewrite_is_flagged(layer):
    agent = _agent(layer, [
        _text("Retention was 88.88% last year."),
        _text("Retention was 88.88%."),
    ])
    result = agent.chat("How's retention?")
    assert result.unverified == ["88.88%"] and result.number_retries == 1
    assert "Automatic check" not in json.dumps(agent.history)


def test_follow_up_may_repeat_an_earlier_tool_number(layer, engine):
    top = _top_rate(engine)
    agent = _agent(layer, [
        _tool("query_metric", RETENTION_BY_FACULTY),
        _text(f"The highest is {top}."),
        _text(f"As I said, {top} was the highest."),
    ])
    agent.chat("Retention by faculty for the 2024 cohort?")
    result = agent.chat("Which was highest again?")
    assert result.unverified == [] and result.number_retries == 0
