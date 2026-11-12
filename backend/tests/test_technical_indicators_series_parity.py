"""The shared indicator series must leave the AI-portfolio gate's snapshots unchanged.

``fixtures/technical_indicator_snapshots_golden.json`` was captured from
``compute_snapshot`` *before* its maths moved into
:mod:`cadence.technical_indicators.series`; the same fixtures must still produce exactly
those snapshots.
"""

from __future__ import annotations

import dataclasses
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from cadence.assets.market_data import HistoryBar
from cadence.technical_indicators.compute import compute_snapshot

_GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "technical_indicator_snapshots_golden.json").read_text()
)


def _fixture(seed: int) -> list[HistoryBar]:
    """Deterministic wavy price walk with a volume pattern (and adjusted closes for seed 2)."""
    bars: list[HistoryBar] = []
    p = 100.0
    for i in range(320):
        p = p * (
            1
            + 0.004 * math.sin(i / 7 + seed)
            + 0.0015 * math.cos(i / 23 * seed + 1)
            + 0.0004 * (seed - 1)
        )
        adj = p * 0.98 if (i % 50 == 0 and seed == 2) else None
        bars.append(
            HistoryBar(
                date=date(2024, 1, 1) + timedelta(days=i),
                close=round(p, 4),
                volume=1_000_000 + (i * 37 % 250) * 1000,
                adj_close=adj,
            )
        )
    return bars


@pytest.mark.parametrize("key", sorted(_GOLDEN))
def test_snapshot_matches_the_pre_refactor_golden_values(key: str) -> None:
    seed, length = (int(part) for part in key.split("-"))
    snapshot = compute_snapshot(_fixture(seed)[:length])

    assert snapshot is not None
    actual = json.loads(json.dumps(dataclasses.asdict(snapshot), default=str))
    assert actual == _GOLDEN[key]
