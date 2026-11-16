"""
Progress reporting: the agent reports each step as it happens, and
/api/chat/stream turns those steps into NDJSON lines ahead of the answer.

No test calls the Anthropic API: the agent runs against the scripted fake
client from test_numbers.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from oirp_agent import web
from oirp_agent.agent import describe_call, describe_outcome

from test_numbers import RETENTION_BY_FACULTY, _agent, _text, _tool, _top_rate, layer  # noqa: F401


def test_steps_are_reported_in_order_including_the_rewrite(layer, engine):
    top = _top_rate(engine)
    agent = _agent(layer, [
        _tool("query_metric", RETENTION_BY_FACULTY),
        _text(f"The highest is {top}, ahead of the lowest by 4.21 points."),
        _text(f"The highest is {top}."),
    ])
    events: list[dict] = []
    result = agent.chat("Retention by faculty for the 2024 cohort?", on_progress=events.append)

    steps = [(e["step"], e.get("phase") or e.get("name") or "") for e in events]
    assert steps == [
        ("model", "read"), ("tool", "query_metric"), ("tool_done", "query_metric"),
        ("model", "tools_back"), ("check", ""), ("model", "rewrite"), ("check", ""),
    ]
    first_check, last_check = (e for e in events if e["step"] == "check")
    assert first_check["missing"] == ["4.21 points"] and not first_check["final"]
    assert last_check["missing"] == [] and last_check["final"] and last_check["checked"] == result.numbers_checked
    assert "Retention cube" in events[1]["label"] and "Faculty" in events[1]["label"]
    assert "row" in events[2]["summary"] and not events[2]["error"]


def test_progress_never_carries_a_measure_value(layer, engine):
    top = _top_rate(engine)
    agent = _agent(layer, [_tool("query_metric", RETENTION_BY_FACULTY), _text(f"The highest is {top}.")])
    events: list[dict] = []
    agent.chat("Retention by faculty for the 2024 cohort?", on_progress=events.append)
    tool_lines = json.dumps([e for e in events if e["step"].startswith("tool")])
    assert top not in tool_lines


def test_a_broken_listener_does_not_break_the_answer(layer):
    def boom(_event):
        raise RuntimeError("listener fell over")

    agent = _agent(layer, [_text("Hello.")])
    assert agent.chat("Hi", on_progress=boom).text == "Hello."
    assert agent._progress is None


def test_labels_read_as_plain_words():
    assert describe_call("query_metric", RETENTION_BY_FACULTY) == (
        "Asking the Retention cube for % Continuing by Faculty: Cohort 2024, Years After 1")
    assert describe_call("get_kpi_value", {"kpi_id": "overall_experience_rating",
                                            "filters": {"cohort": "first_year"}}) == (
        "Looking up the published figure for overall experience rating (first year)")
    assert describe_call("describe_cube", {}) == "Listing the warehouse cubes"
    assert describe_outcome("get_kpi_value", {"records": []}) == "Not in the published data"
    assert "adjusting" in describe_outcome("query_metric", {"error": "no such level"})


@pytest.fixture
def client(monkeypatch):
    """A test client whose every session uses the agent a test puts on `client.agent`."""
    c = TestClient(web.app)
    monkeypatch.setattr(web, "_get_or_create_agent", lambda _session_id: c.agent)
    return c


def _lines(resp):
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_stream_sends_progress_then_one_answer(client, layer, engine):
    top = _top_rate(engine)
    client.agent = _agent(layer, [_tool("query_metric", RETENTION_BY_FACULTY), _text(f"The highest is {top}.")])
    resp = client.post("/api/chat/stream", json={"message": "Retention by faculty for 2024?"})

    assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/x-ndjson")
    assert web.SESSION_COOKIE in resp.cookies
    lines = _lines(resp)
    assert [e["event"] for e in lines[:-1]] == ["progress"] * (len(lines) - 1)
    answer = lines[-1]
    assert answer["event"] == "answer" and answer["text"] == f"The highest is {top}."
    assert answer["numbers_checked"] == 1 and answer["tables"][0]["kind"] == "synthetic"


def test_stream_reports_errors_as_a_line(client, layer):
    client.agent = _agent(layer, [])          # the fake client has nothing to say: IndexError
    lines = _lines(client.post("/api/chat/stream", json={"message": "Hi"}))
    assert lines[-1]["event"] == "error" and lines[-1]["error"] == "IndexError"
