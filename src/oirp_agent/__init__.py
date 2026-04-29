"""OIRP-chat: a semantic-layer-grounded chat agent for institutional research data.

Portfolio demo. Inspired by Fullscript's Flurry architecture, scaled down to
public OIRP-style data.

Note: The OIRPAgent class lives in `oirp_agent.agent` and pulls in the
`anthropic` SDK. The loader, store, and confidence modules don't need the
SDK and can be imported standalone (e.g., for evals, tests, or static
prompt inspection without making API calls).
"""

from .confidence import ConfidenceTier, TurnTrace
from .kpi_store import KPIStore
from .prompt_loader import (
    KPIDocument,
    assemble_system_prompt,
    load_kpi_document,
    load_semantic_layer,
)

__version__ = "0.1.0"

__all__ = [
    "ConfidenceTier",
    "TurnTrace",
    "KPIStore",
    "KPIDocument",
    "assemble_system_prompt",
    "load_kpi_document",
    "load_semantic_layer",
]
