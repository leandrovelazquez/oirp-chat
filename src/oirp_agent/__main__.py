"""
CLI entry point for the OIRP agent.

Usage:
    export ANTHROPIC_API_KEY=...
    python -m oirp_agent

Optional flags:
    --semantic-layer PATH    Override the path to the semantic_layer/ directory
    --model MODEL_ID         Override the model (default: claude-opus-4-7)
    --once "QUESTION"        Single-shot mode (don't enter the REPL)
    --show-trace             Print the per-turn tool trace alongside the response
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .agent import DEFAULT_MODEL, OIRPAgent
from .confidence import ConfidenceTier


def _confidence_badge(tier: ConfidenceTier) -> str:
    colors = {
        ConfidenceTier.HIGH: "bold green",
        ConfidenceTier.MEDIUM: "bold yellow",
        ConfidenceTier.LOW: "bold red",
        ConfidenceTier.NONE: "dim",
    }
    label = {
        ConfidenceTier.HIGH: "HIGH — verified lookup",
        ConfidenceTier.MEDIUM: "MEDIUM — methodology / synthesis",
        ConfidenceTier.LOW: "LOW — verified store missed; check refusal",
        ConfidenceTier.NONE: "NONE — no tools fired",
    }
    return f"[{colors[tier]}]{label[tier]}[/]"


def _print_trace(console: Console, agent: OIRPAgent, result) -> None:
    if not result.trace.calls:
        console.print("[dim]No tools fired this turn.[/]")
        return
    table = Table(title="Tool trace", show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("Tool")
    table.add_column("Summary")
    for i, call in enumerate(result.trace.calls, start=1):
        table.add_row(str(i), call.name, call.result_summary)
    console.print(table)


def _print_loaded_summary(console: Console, agent: OIRPAgent) -> None:
    table = Table(title="Semantic layer loaded", show_header=True, header_style="bold")
    table.add_column("KPI ID")
    table.add_column("Domain")
    table.add_column("Status")
    table.add_column("Records")
    for doc in agent.documents:
        record_count = sum(len(b) for b in doc.json_blocks)
        status_color = {
            "verified": "green",
            "partial": "yellow",
            "stub": "dim",
            "deprecated": "red",
        }.get(doc.status, "white")
        table.add_row(
            doc.kpi_id,
            doc.domain,
            f"[{status_color}]{doc.status}[/]",
            str(record_count),
        )
    console.print(table)
    total_records = len(agent.store.records)
    total_sections = len(agent.store.prose_sections)
    console.print(
        f"[dim]Total: {len(agent.documents)} KPIs, "
        f"{total_records} verified records, "
        f"{total_sections} prose sections.[/]\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="oirp-agent")
    parser.add_argument(
        "--semantic-layer",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "semantic_layer",
        help="Path to the semantic_layer/ directory (default: ../../semantic_layer).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model id.")
    parser.add_argument("--once", help="Run a single question and exit.")
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="Print the per-turn tool trace.",
    )
    args = parser.parse_args()

    console = Console()
    sl_dir = args.semantic_layer
    base_prompt = sl_dir / "base_prompt.md"
    kpi_dir = sl_dir / "kpis"

    if not base_prompt.exists():
        console.print(f"[red]Missing base prompt at {base_prompt}[/]")
        sys.exit(1)
    if not kpi_dir.exists():
        console.print(f"[red]Missing kpis/ directory at {kpi_dir}[/]")
        sys.exit(1)

    agent = OIRPAgent(
        semantic_layer_dir=kpi_dir,
        base_prompt_path=base_prompt,
        model=args.model,
    )
    _print_loaded_summary(console, agent)

    if args.once:
        _ask(console, agent, args.once, show_trace=args.show_trace)
        return

    console.print(
        Panel(
            "Ask questions about Carleton OIRP-style KPIs. "
            "Type 'reset' to clear conversation history, 'quit' or Ctrl-D to exit.",
            title="OIRP-chat",
            border_style="cyan",
        )
    )
    while True:
        try:
            user = console.input("\n[bold cyan]you ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not user:
            continue
        if user.lower() in {"quit", "exit"}:
            break
        if user.lower() == "reset":
            agent.reset()
            console.print("[dim]Conversation history cleared.[/]")
            continue
        _ask(console, agent, user, show_trace=args.show_trace)


def _ask(console: Console, agent: OIRPAgent, message: str, show_trace: bool) -> None:
    result = agent.chat(message)
    console.print()
    console.print(Markdown(result.text or "_(empty response)_"))
    console.print(f"\nConfidence: {_confidence_badge(result.confidence)}")
    if show_trace:
        _print_trace(console, agent, result)


if __name__ == "__main__":
    main()
