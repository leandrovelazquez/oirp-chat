"""
Structured "can't answer" reasons (item 5) and preliminary results (item 6).

No test calls the Anthropic API: the agent runs against the scripted fake
client from test_numbers.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from oirp_agent import cannot_answer
from oirp_agent.agent import MAX_TOOL_ROUNDS
from oirp_agent.confidence import ConfidenceTier, TurnTrace
from oirp_agent.evals import score
from oirp_agent.numbers import model_payload, warehouse_table

from test_numbers import _agent, _retention, _text, _tool, layer  # noqa: F401

PERSON = """No answer is ever given about an individual student.

<cannot_answer reason="person">
<ask>What share of BIOL 1001 students passed in fall 2025?</ask>
<ask>  What was first-year retention
  in the Faculty of Science for the 2024 cohort? </ask>
</cannot_answer>"""


# ---- reading the block ------------------------------------------------------


def test_block_is_read_and_removed():
    text, reason, asks = cannot_answer.split(PERSON)
    assert text == "No answer is ever given about an individual student."
    assert reason == "person"
    assert asks == ["What share of BIOL 1001 students passed in fall 2025?",
                    "What was first-year retention in the Faculty of Science for the 2024 cohort?"]


def test_no_block_means_it_answered():
    assert cannot_answer.split("Retention was 90.7%.") == ("Retention was 90.7%.", None, [])


def test_unknown_reason_is_dropped_but_suggestions_kept():
    _, reason, asks = cannot_answer.split('x <cannot_answer reason="because"><ask>Q?</ask></cannot_answer>')
    assert reason is None and asks == ["Q?"]


def test_the_model_cannot_claim_a_code_reason():
    _, reason, _ = cannot_answer.split('x <cannot_answer reason="unverified"><ask>Q?</ask></cannot_answer>')
    assert reason is None


def test_unclosed_block_is_still_removed_and_at_most_three_asks():
    raw = "Which one?\n<cannot_answer reason='unclear'>" + "".join(f"<ask>Q{i}?</ask>" for i in range(5))
    text, reason, asks = cannot_answer.split(raw)
    assert text == "Which one?" and reason == "unclear" and asks == ["Q0?", "Q1?", "Q2?"]


# ---- the agent --------------------------------------------------------------


def test_agent_returns_the_reason_and_hides_the_block(layer):
    agent = _agent(layer, [_text(PERSON)])
    result = agent.chat("What grade did student 101234567 get in BIOL 1001?")
    assert result.could_not_answer == "person" and len(result.suggestions) == 2
    assert "<cannot_answer" not in result.text and "<ask>" not in result.text
    # The suggested questions' numbers aren't claims, so they aren't checked.
    assert result.unverified == []


def test_a_number_still_unsupported_after_the_rewrite_is_unverified(layer):
    agent = _agent(layer, [_text("Retention was 88.88%."), _text("Retention was 88.88%.")])
    result = agent.chat("How's retention?")
    assert result.could_not_answer == "unverified"


def test_running_out_of_tool_rounds_is_a_limit(layer):
    script = [_tool("describe_cube", {}, id_=f"tu_{i}") for i in range(MAX_TOOL_ROUNDS)] + [_text("I ran out of steps.")]
    result = _agent(layer, script).chat("Tell me everything.")
    assert result.could_not_answer == "limit"


TINY = {"cube": "Retention", "measures": ["% Continuing"],
        "filters": {"Cohort": 2025, "Years After": 1, "1st Academic Unit": "Music",
                    "Region.Category": "International"}}


def test_every_cell_suppressed_is_a_limit_even_if_the_model_says_nothing(layer, engine):
    r = engine.query(TINY["cube"], TINY["measures"], filters=TINY["filters"])
    assert r["rows"] and all(row.get("suppressed") for row in r["rows"])   # the premise
    result = _agent(layer, [_tool("query_metric", TINY), _text("That cell is suppressed.")]).chat("Music, intl, 2025?")
    assert result.could_not_answer == "limit"


def test_a_no_data_or_limit_label_on_shown_warehouse_numbers_is_dropped(layer):
    for reason in ("no_data", "limit"):
        result = _agent(layer, [
            _tool("query_metric", {"cube": "Retention", "measures": ["% Continuing"],
                                   "filters": {"Cohort": 2022, "Years After": 1}}),
            _text(f'Shown below (synthetic).\n<cannot_answer reason="{reason}"><ask>Q?</ask></cannot_answer>'),
        ]).chat("Retention for the 2022 cohort?")
        assert result.could_not_answer is None and result.suggestions == []
        assert result.follow_ups                      # it answered, so the next questions show


def test_the_label_stays_when_nothing_was_shown_or_it_is_about_a_person(layer):
    no_rows = _agent(layer, [_text('Not covered.\n<cannot_answer reason="no_data"><ask>Q?</ask></cannot_answer>')])
    assert no_rows.chat("How many staff?").could_not_answer == "no_data"
    person = _agent(layer, [
        _tool("query_metric", {"cube": "Retention", "measures": ["% Continuing"],
                               "filters": {"Cohort": 2022, "Years After": 1}}),
        _text('No.\n<cannot_answer reason="person"><ask>Q?</ask></cannot_answer>'),
    ])
    assert person.chat("What did student 1 get?").could_not_answer == "person"


def test_a_figure_from_the_verified_documents_needs_no_rewrite(layer):
    # Hard rule 4 tells the model NSSE effect sizes were all < 0.3; quoting it is fine.
    assert "0.3" in layer.system_prompt
    result = _agent(layer, [_text("The differences are small: effect sizes were all below 0.3.")]).chat("Big gaps?")
    assert result.number_retries == 0 and result.unverified == []


def test_the_numbers_behind_a_rewrite_are_recorded(layer):
    result = _agent(layer, [_text("Retention was 88.88%."), _text("Retention was 88.88%.")]).chat("How's retention?")
    assert result.rewritten_for == ["88.88%"]


def test_an_answer_has_no_reason(layer):
    result = _agent(layer, [_text("Hello.")]).chat("Hi")
    assert result.could_not_answer is None and result.suggestions == []


# ---- the eval check ---------------------------------------------------------


def _result(reason=None, suggestions=()):
    return SimpleNamespace(text="t", trace=TurnTrace(), confidence=ConfidenceTier.NONE, tables=[],
                           unverified=[], could_not_answer=reason, suggestions=list(suggestions))


def test_eval_checks_the_reason_and_wants_a_suggestion():
    assert score({"expected_could_not_answer": "person"}, _result("person", ["Q?"]), None)["reason"][0]
    assert not score({"expected_could_not_answer": "person"}, _result("person"), None)["reason"][0]
    assert not score({"expected_could_not_answer": "no_data"}, _result("person", ["Q?"]), None)["reason"][0]
    assert score({"expected_could_not_answer": "none"}, _result(), None)["reason"][0]
    assert not score({"expected_could_not_answer": "none"}, _result("limit", ["Q?"]), None)["reason"][0]


# ---- preliminary ------------------------------------------------------------


def test_fall_2026_is_preliminary_and_fall_2025_is_not(engine):
    now = engine.query("Enrolment", ["Student Count"], filters={"Time": "Fall 2026"})
    assert now["preliminary"][0]["applies_to"] == "Time = Fall 2026"
    assert now["rows"][0]["preliminary"] is True
    before = engine.query("Enrolment", ["Student Count"], filters={"Time": "Fall 2025"})
    assert "preliminary" not in before and "preliminary" not in before["rows"][0]


def test_only_the_preliminary_rows_of_a_trend_are_marked(engine):
    r = engine.query("Enrolment", ["Student Count"], by=["Time"], filters={"Time.Semester": "Fall"})
    marked = [row["Time"] for row in r["rows"] if row.get("preliminary")]
    assert marked == ["Fall 2026"]
    table = warehouse_table(r)
    assert table["preliminary"] and table["row_preliminary"].count(True) == 1
    assert any(n.startswith("Preliminary (Time = Fall 2026)") for n in table["notes"])


def test_retention_outcomes_observed_in_2026_27_are_preliminary(engine):
    r = engine.query("Retention", ["% Continuing"], by=["Cohort"], filters={"Years After": 1})
    marked = [row["Cohort (dimension)"] if "Cohort (dimension)" in row else row["Cohort"]
              for row in r["rows"] if row.get("preliminary")]
    assert [str(m) for m in marked] == ["2025"]
    assert "preliminary" not in _retention(engine)   # cohort 2024's year 1 is 2025/26: final


def test_the_model_is_told_which_rows_are_preliminary(engine):
    r = engine.query("Enrolment", ["Student Count"], filters={"Time": "Fall 2026"})
    payload = json.loads(model_payload("query_metric", r))
    assert payload["preliminary"][0]["why"] and payload["rows"][0]["preliminary"] is True
