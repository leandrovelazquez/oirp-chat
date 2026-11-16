from __future__ import annotations

from pathlib import Path

import pytest

from oirp_agent.synthetic_warehouse import DEFAULT_DB_PATH, ensure_built
from oirp_agent.warehouse import WarehouseEngine, load_cubes

ROOT = Path(__file__).resolve().parents[1]
SL = ROOT / "semantic_layer"


@pytest.fixture(scope="session")
def engine() -> WarehouseEngine:
    """The synthetic warehouse (built on first use, about a minute)."""
    ensure_built(DEFAULT_DB_PATH)
    return WarehouseEngine(DEFAULT_DB_PATH, load_cubes(SL / "warehouse"))
