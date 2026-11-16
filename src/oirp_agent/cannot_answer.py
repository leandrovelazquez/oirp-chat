"""
Structured "can't answer" reasons.

When the assistant can't answer, it ends its reply with a short block the page
reads instead of a dead end:

    <cannot_answer reason="person">
    <ask>How many students were enrolled in BIOL 1001 in fall 2025?</ask>
    </cannot_answer>

The block is stripped from the text the user sees; the reason becomes a label
on the card and each <ask> a button that asks it.

The code also sets a reason when the model gave none (agent._code_reason):
`unverified` when a number still couldn't be traced to a tool after the
rewrite (only the code sets this one), and `limit` when the tool budget ran out
or every warehouse cell returned was suppressed.
"""

from __future__ import annotations

import re

# What the model may say, and what the code adds.
MODEL_REASONS = {
    "no_data": "Nothing in the published reports or the warehouse covers it.",
    "person": "It's about one person; no answer is ever given about an individual.",
    "limit": "A rule stops it: every cell needed is too small to show, or it would "
             "compare synthetic with published figures.",
    "unclear": "It can be read in ways that give different numbers.",
}
REASONS = {**MODEL_REASONS, "unverified": "A number in the answer couldn't be traced to the data."}

MAX_SUGGESTIONS = 3

_BLOCK = re.compile(r"<cannot_answer\b(?P<attrs>[^>]*)>(?P<body>.*?)(?:</cannot_answer>|\Z)", re.S | re.I)
_REASON = re.compile(r"""reason\s*=\s*["']?(?P<r>[a-z_]+)""", re.I)
_ASK = re.compile(r"<ask>(?P<q>.*?)</ask>", re.S | re.I)


def split(text: str) -> tuple[str, str | None, list[str]]:
    """(the text without the block, the reason or None, the suggested questions).

    An unknown reason is dropped, but its suggestions are kept. A block left
    unclosed at the end of the text is still removed.
    """
    reason: str | None = None
    asks: list[str] = []
    for m in _BLOCK.finditer(text):
        r = _REASON.search(m.group("attrs") or "")
        if r and r.group("r").lower() in MODEL_REASONS and reason is None:
            reason = r.group("r").lower()
        for a in _ASK.finditer(m.group("body") or ""):
            q = " ".join(a.group("q").split())
            if q and q not in asks:
                asks.append(q)
    clean = _BLOCK.sub("", text).rstrip()
    return clean, reason, asks[:MAX_SUGGESTIONS]
