"""Architecture guard: broker orders are only ever placed through the order gateway.

Any ``<something>broker.buy(`` / ``.sell(`` / ``.submit_order(`` outside the broker
package and :mod:`cadence.orders` would bypass the write-ahead journal and the long-only
guard — the bypass that let failed bot ticks leave unrecorded orders and shorts behind.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "cadence"
_ALLOWED = {_SRC / "broker", _SRC / "orders"}
_DIRECT_ORDER = re.compile(r"\b_?broker\.(buy|sell|submit_order)\(")


def _offenders(root: Path) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*.py"):
        if any(allowed in path.parents for allowed in _ALLOWED):
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if _DIRECT_ORDER.search(line):
                hits.append(f"{path.relative_to(root)}:{number}: {line.strip()}")
    return hits


def test_no_direct_broker_orders_outside_the_gateway() -> None:
    assert _offenders(_SRC) == []


def test_guard_detects_a_planted_direct_call(tmp_path: Path) -> None:
    (tmp_path / "rogue.py").write_text("def f(broker):\n    return broker.sell('AAPL', 1)\n")
    (tmp_path / "fine.py").write_text("def g(gateway):\n    return gateway.sell('AAPL', 1)\n")

    assert _offenders(tmp_path) == ["rogue.py:2: return broker.sell('AAPL', 1)"]
