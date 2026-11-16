"""
What the 5.x models need from the agent loop: thinking blocks passed back
unchanged, a history that stays valid for them after a number-check rewrite,
effort sent explicitly, and a safety decline handled before reading content.

No test calls the Anthropic API: the agent runs against the scripted fake
client from test_numbers.
"""

from __future__ import annotations

from types import SimpleNamespace

from oirp_agent.agent import REFUSAL_TEXT

from test_numbers import RETENTION_BY_FACULTY, _agent, _top_rate, layer  # noqa: F401


class Block(SimpleNamespace):
    """A content block with model_dump, like the SDK's."""

    def model_dump(self, mode="python", exclude_none=False):
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def _thinking(sig):
    return Block(type="thinking", thinking="", signature=sig)


def _resp(*blocks, stop="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop)


def _text(t):
    return Block(type="text", text=t)


def _tool(inp, id_="tu_1"):
    return Block(type="tool_use", id=id_, name="query_metric", input=inp)


def _thinking_sigs(history):
    return [b["signature"] for m in history if m["role"] == "assistant"
            for b in m["content"] if b.get("type") == "thinking"]


def test_thinking_blocks_go_back_unchanged_and_text_is_read_by_type(layer, engine):
    top = _top_rate(engine)
    agent = _agent(layer, [
        _resp(_thinking("s1"), _tool(RETENTION_BY_FACULTY), stop="tool_use"),
        _resp(_thinking("s2"), _text(f"The highest is {top}.")),
    ])
    result = agent.chat("Retention by faculty?")
    assert result.text == f"The highest is {top}."
    # The second request carried the first turn's thinking block, empty text and all.
    sent = agent.client.requests[1][1]["content"][0]
    assert sent == {"type": "thinking", "thinking": "", "signature": "s1"}
    assert _thinking_sigs(agent.history) == ["s1", "s2"]


def test_after_a_rewrite_only_the_rewrites_thinking_is_dropped(layer, engine):
    top = _top_rate(engine)
    agent = _agent(layer, [
        _resp(_thinking("before"), _tool(RETENTION_BY_FACULTY), stop="tool_use"),
        _resp(_thinking("failed"), _text(f"The highest is {top}, ahead by 4.21 points.")),
        _resp(_thinking("rewrite"), _text(f"The highest is {top}.")),
    ])
    result = agent.chat("Retention by faculty?")
    assert result.number_retries == 1 and result.unverified == []
    # The block written before the edit stays (its history is unchanged); the
    # failed draft is gone, and the rewrite's block, written after the
    # deleted draft, is removed so nothing invalid is replayed.
    assert _thinking_sigs(agent.history) == ["before"]
    assert agent.history[-1]["content"] == [{"type": "text", "text": f"The highest is {top}."}]


def test_effort_is_sent_when_set_and_not_otherwise(layer):
    agent = _agent(layer, [_resp(_text("Hi."))])
    seen = []
    create = agent.client.create
    agent.client.create = lambda **kw: (seen.append(kw), create(**kw))[1]
    agent.chat("Hi")
    assert seen[0]["output_config"] == {"effort": "medium"} and seen[0]["max_tokens"] >= 16000

    quiet = _agent(layer, [_resp(_text("Hi."))])
    quiet.effort = None
    seen.clear()
    create2 = quiet.client.create
    quiet.client.create = lambda **kw: (seen.append(kw), create2(**kw))[1]
    quiet.chat("Hi")
    assert "output_config" not in seen[0]


def test_a_safety_decline_shows_a_plain_message_and_the_conversation_goes_on(layer):
    agent = _agent(layer, [_resp(_thinking("x"), stop="refusal"), _resp(_text("Hello again."))])
    result = agent.chat("Something declined")
    assert result.text == REFUSAL_TEXT and result.raw_stop_reason == "refusal"
    assert agent.chat("Hi").text == "Hello again."
