"""
The agent loop.

We use the lower-level Anthropic Messages API and implement the tool loop by
hand rather than using the SDK's `tool_runner` convenience wrapper. The manual
loop is more lines of code, but for a portfolio project the explicitness is
the point: anyone reading agent.py can see exactly how tool-calling, conversation
history, and confidence tracking fit together.

Architecture per turn:

  1. Append the user's message to conversation history.
  2. Send messages.create() with the system prompt, tool schemas, and history.
  3. If stop_reason == "tool_use", execute every tool_use block in the
     response, package the results as tool_result content blocks, and loop.
  4. If stop_reason == "end_turn", we have the final assistant message;
     compute the confidence tier and return.

The system prompt is assembled once at agent construction (it includes all
KPI files concatenated). Conversation history accumulates across user turns
but resets when the caller starts a new conversation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from .confidence import ConfidenceTier, TurnTrace
from .kpi_store import KPIStore
from .prompt_loader import (
    KPIDocument,
    assemble_system_prompt,
    load_semantic_layer,
)
from .tools import TOOL_SCHEMAS, ToolDispatcher
from .warehouse import Cube, WarehouseEngine, load_cubes


# Default model. Easy to override at construction time.
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096

# Safety bound on the inner tool loop to avoid runaway calls. Warehouse
# questions can take describe -> query -> corrected query, so leave headroom.
MAX_TOOL_ROUNDS = 10


@dataclass
class SemanticLayer:
    """Everything loaded once and shared read-only across conversations."""

    documents: list[KPIDocument]
    store: KPIStore
    cubes: list[Cube]
    engine: WarehouseEngine | None
    system_prompt: str

    @classmethod
    def load(
        cls,
        kpi_dir: Path,
        base_prompt_path: Path,
        warehouse_dir: Path | None = None,
        warehouse_db: Path | None = None,
        build_if_missing: bool = True,
    ) -> "SemanticLayer":
        documents = load_semantic_layer(kpi_dir)
        store = KPIStore(documents)
        cubes: list[Cube] = []
        engine: WarehouseEngine | None = None
        if warehouse_dir is None:
            warehouse_dir = kpi_dir.parent / "warehouse"
        if warehouse_dir.exists():
            cubes = load_cubes(warehouse_dir)
        if cubes:
            from .synthetic_warehouse import DEFAULT_DB_PATH, ensure_built

            db = warehouse_db or DEFAULT_DB_PATH
            if build_if_missing:
                ensure_built(db)
            if db.exists():
                engine = WarehouseEngine(db, cubes)
        system_prompt = assemble_system_prompt(
            base_prompt_path, documents,
            [(c.name, c.raw_markdown) for c in cubes] if engine else None,
        )
        return cls(documents, store, cubes, engine, system_prompt)


@dataclass
class TurnResult:
    """Outcome of one user-message → assistant-response cycle."""

    text: str
    confidence: ConfidenceTier
    trace: TurnTrace
    raw_stop_reason: str | None = None


@dataclass
class OIRPAgent:
    semantic_layer_dir: Path
    base_prompt_path: Path
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    # Pass a pre-loaded layer to share it across agents (the web server does).
    layer: SemanticLayer | None = None

    # Filled in __post_init__:
    documents: list[KPIDocument] = field(init=False)
    store: KPIStore = field(init=False)
    engine: WarehouseEngine | None = field(init=False)
    dispatcher: ToolDispatcher = field(init=False)
    system_prompt: str = field(init=False)
    client: Anthropic = field(init=False)
    history: list[dict] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        if self.layer is None:
            self.layer = SemanticLayer.load(self.semantic_layer_dir, self.base_prompt_path)
        self.documents = self.layer.documents
        self.store = self.layer.store
        self.engine = self.layer.engine
        self.dispatcher = ToolDispatcher(self.store, self.engine)
        self.system_prompt = self.layer.system_prompt
        self.client = Anthropic()
        self.history = []

    # ----- public API -----

    def chat(self, user_message: str) -> TurnResult:
        """Run one user turn through the tool loop and return the final response."""
        self.history.append({"role": "user", "content": user_message})
        trace = TurnTrace()

        last_stop_reason: str | None = None
        tools = TOOL_SCHEMAS if self.engine is not None else [
            t for t in TOOL_SCHEMAS if t["name"] not in ("query_metric", "describe_cube")
        ]

        for round_no in range(MAX_TOOL_ROUNDS + 1):
            # On the last round, forbid tools so the turn always ends in text.
            extra = {"tool_choice": {"type": "none"}} if round_no == MAX_TOOL_ROUNDS else {}
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=tools,
                messages=self.history,
                **extra,
            )

            # Persist the assistant turn (model output) to history regardless of
            # stop_reason — the API requires the full prior assistant message
            # when we send back tool_result blocks.
            self.history.append(
                {"role": "assistant", "content": _serialize_content(response.content)}
            )
            last_stop_reason = response.stop_reason

            if response.stop_reason == "tool_use":
                tool_result_blocks = self._execute_tool_calls(response.content, trace)
                # Tool results are returned in a single user turn.
                self.history.append({"role": "user", "content": tool_result_blocks})
                continue

            # Any other stop_reason = we're done with this turn.
            break

        text = _extract_text(self.history[-1]["content"])
        return TurnResult(
            text=text,
            confidence=trace.confidence,
            trace=trace,
            raw_stop_reason=last_stop_reason,
        )

    def reset(self) -> None:
        """Drop conversation history (semantic layer & client are kept)."""
        self.history = []

    # ----- internals -----

    def _execute_tool_calls(
        self,
        assistant_content: list[Any],
        trace: TurnTrace,
    ) -> list[dict]:
        """Run every tool_use block in the assistant message; return tool_result blocks."""
        results: list[dict] = []
        for block in assistant_content:
            block_type = getattr(block, "type", None)
            if block_type != "tool_use":
                continue

            name = block.name
            tool_input = block.input
            tool_use_id = block.id

            result = self.dispatcher.dispatch(name, tool_input)

            # Record for confidence tracking.
            if name == "get_kpi_value":
                trace.record_get_kpi_value(tool_input, result)
            elif name == "search_methodology":
                trace.record_search_methodology(tool_input, result)
            elif name == "list_kpis":
                trace.record_list_kpis(tool_input, result)
            elif name == "query_metric":
                trace.record_query_metric(tool_input, result)
            elif name == "describe_cube":
                trace.record_describe_cube(tool_input, result)
            else:
                trace.record_generic(name, tool_input, result)

            # The compiled SQL is for the trace/UI, not the model.
            payload = {k: v for k, v in result.items() if k != "sql"}
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(payload, default=str),
                    **({"is_error": True} if "error" in result else {}),
                }
            )
        return results


# ---------- helpers for serializing API objects into history ----------


def _serialize_content(content: list[Any]) -> list[dict]:
    """Turn the API's response content blocks into plain dicts for history reuse.

    The Anthropic SDK returns typed objects; we round-trip through plain dicts
    so the same structure can be sent back as part of `messages` on the next
    request.
    """
    out = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            out.append({"type": "text", "text": block.text})
        elif block_type == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
        else:
            # Fallback for any future block types we don't recognize yet.
            d = (
                block.model_dump()
                if hasattr(block, "model_dump")
                else dict(block)
            )
            out.append(d)
    return out


def _extract_text(content: list[dict]) -> str:
    """Pull all text blocks out of a serialized assistant message."""
    parts = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n\n".join(parts).strip()
