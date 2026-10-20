"""Unit tests for the company-fundamentals derivation + attach helpers.

These exercise the pure derivation helper, the unavailable-marker logic, the
version constant, and the gate-controlled attachment onto candidate/holding dicts
in isolation — no DB, no agent. The end-to-end v4/opt-in gating is covered by the
flow tests in ``test_ai_portfolio_service.py``.
"""

from __future__ import annotations

from typing import Any

from cadence.ai_portfolio._helpers import (
    _build_holdings,
    _candidates_from_universe,
    _derive_fundamentals_figures,
    _fundamentals_annotation,
)
from cadence.ai_portfolio.constants import (
    FUNDAMENTALS_PROMPT_VERSION,
    TREND_PROMPT_VERSION,
)
from cadence.assets.fundamentals import FundamentalsStatus
from cadence.assets.models import Asset, AssetFundamentals
from cadence.broker.stub import StubBroker
from cadence.paper_trading.models import SessionPosition


def _figure(value: float) -> dict[str, Any]:
    return {"value": value, "unit": "USD"}


# --------------------------------------------------------------------------- #
# Derivation helper (task 1.1)
# --------------------------------------------------------------------------- #


def test_derive_fundamentals_full_figures() -> None:
    derived = _derive_fundamentals_figures(
        {
            "revenue": _figure(1000.0),
            "gross_profit": _figure(400.0),
            "operating_income": _figure(250.0),
            "net_income": _figure(200.0),
            "operating_cash_flow": _figure(300.0),
            "eps_diluted": _figure(5.5),
            "eps_basic": _figure(5.7),
        }
    )
    assert derived["status"] == "available"
    assert derived["gross_margin"] == 0.4
    assert derived["operating_margin"] == 0.25
    assert derived["net_margin"] == 0.2
    # Diluted EPS wins over basic when present.
    assert derived["eps"] == 5.5
    assert derived["revenue"] == 1000.0
    assert derived["net_income"] == 200.0
    assert derived["operating_cash_flow"] == 300.0


def test_derive_fundamentals_falls_back_to_basic_eps() -> None:
    derived = _derive_fundamentals_figures(
        {"revenue": _figure(100.0), "eps_basic": _figure(2.0)}
    )
    assert derived["eps"] == 2.0


def test_derive_fundamentals_zero_or_missing_revenue_omits_margins() -> None:
    # Zero revenue: margins omitted (no divide-by-zero), scale figures still present.
    zero_rev = _derive_fundamentals_figures(
        {"revenue": _figure(0.0), "net_income": _figure(50.0)}
    )
    assert "gross_margin" not in zero_rev
    assert "operating_margin" not in zero_rev
    assert "net_margin" not in zero_rev
    assert zero_rev["net_income"] == 50.0
    assert zero_rev["revenue"] == 0.0

    # Missing revenue entirely: margins omitted, no revenue key.
    no_rev = _derive_fundamentals_figures({"net_income": _figure(50.0)})
    assert "net_margin" not in no_rev
    assert "revenue" not in no_rev
    assert no_rev["net_income"] == 50.0


def test_derive_fundamentals_missing_income_figures_omits_those_margins() -> None:
    derived = _derive_fundamentals_figures(
        {"revenue": _figure(1000.0), "gross_profit": _figure(400.0)}
    )
    # Only the margin whose income figure is present is reported.
    assert derived["gross_margin"] == 0.4
    assert "operating_margin" not in derived
    assert "net_margin" not in derived
    assert "net_income" not in derived
    assert "eps" not in derived


# --------------------------------------------------------------------------- #
# Unavailable marker (task 1.2)
# --------------------------------------------------------------------------- #


def _fundamentals_record(
    status: FundamentalsStatus, figures: dict[str, Any] | None = None
) -> AssetFundamentals:
    return AssetFundamentals(
        source="sec_edgar",
        status=status.value,
        cik="1",
        document={"figures": figures or {}},
    )


def test_fundamentals_annotation_none_record_is_unavailable() -> None:
    assert _fundamentals_annotation(None) == {"status": "unavailable"}


def test_fundamentals_annotation_non_available_status_is_unavailable() -> None:
    for status in (FundamentalsStatus.PARTIAL, FundamentalsStatus.UNAVAILABLE):
        record = _fundamentals_record(status, {"revenue": _figure(100.0)})
        assert _fundamentals_annotation(record) == {"status": "unavailable"}


def test_fundamentals_annotation_available_derives_figures() -> None:
    record = _fundamentals_record(
        FundamentalsStatus.AVAILABLE,
        {"revenue": _figure(100.0), "net_income": _figure(10.0)},
    )
    annotation = _fundamentals_annotation(record)
    assert annotation["status"] == "available"
    assert annotation["net_margin"] == 0.1


def test_fundamentals_annotation_markers_are_independent_copies() -> None:
    # Each unavailable marker is a fresh dict so callers never share mutable state.
    a = _fundamentals_annotation(None)
    b = _fundamentals_annotation(None)
    assert a == b
    a["mutated"] = True
    assert "mutated" not in b


# --------------------------------------------------------------------------- #
# Version constant (task 4.1)
# --------------------------------------------------------------------------- #


def test_fundamentals_prompt_version_is_after_trend() -> None:
    assert FUNDAMENTALS_PROMPT_VERSION > TREND_PROMPT_VERSION
    assert FUNDAMENTALS_PROMPT_VERSION == 4


# --------------------------------------------------------------------------- #
# Candidate attach gate (task 5.1)
# --------------------------------------------------------------------------- #


def _asset(
    ticker: str, fundamentals: AssetFundamentals | None = None
) -> Asset:
    return Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        is_eligible=True,
        fundamentals=fundamentals,
    )


def test_candidates_attach_fundamentals_when_enabled() -> None:
    assets = [
        _asset(
            "AAPL",
            _fundamentals_record(
                FundamentalsStatus.AVAILABLE,
                {"revenue": _figure(100.0), "net_income": _figure(10.0)},
            ),
        ),
        _asset("NOFUND", None),
    ]
    candidates, _ = _candidates_from_universe(
        assets, {}, apply_gate=False, fundamentals=True
    )
    by_ticker = {c["ticker"]: c for c in candidates}
    assert by_ticker["AAPL"]["fundamentals"]["status"] == "available"
    assert by_ticker["AAPL"]["fundamentals"]["net_margin"] == 0.1
    # No stored record -> explicit unavailable marker, not invented figures.
    assert by_ticker["NOFUND"]["fundamentals"] == {"status": "unavailable"}


def test_candidates_omit_fundamentals_when_disabled() -> None:
    assets = [_asset("AAPL", _fundamentals_record(FundamentalsStatus.AVAILABLE))]
    candidates, _ = _candidates_from_universe(
        assets, {}, apply_gate=False, fundamentals=False
    )
    assert all("fundamentals" not in c for c in candidates)


# --------------------------------------------------------------------------- #
# Holding attach gate (task 5.2)
# --------------------------------------------------------------------------- #


def _ledger(*tickers: str) -> list[SessionPosition]:
    return [
        SessionPosition(ticker=t, quantity=10.0, avg_cost=50.0) for t in tickers
    ]


def test_holdings_attach_fundamentals_when_map_given() -> None:
    broker = StubBroker()
    holdings = _build_holdings(
        _ledger("AAPL", "MSFT"),
        broker,
        {},
        fundamentals_by_ticker={"AAPL": {"status": "available", "net_margin": 0.2}},
    )
    by_ticker = {h["ticker"]: h for h in holdings}
    assert by_ticker["AAPL"]["fundamentals"] == {
        "status": "available",
        "net_margin": 0.2,
    }
    # A held ticker absent from the map falls back to the unavailable marker.
    assert by_ticker["MSFT"]["fundamentals"] == {"status": "unavailable"}


def test_holdings_omit_fundamentals_when_map_none() -> None:
    broker = StubBroker()
    holdings = _build_holdings(_ledger("AAPL"), broker, {})
    assert all("fundamentals" not in h for h in holdings)
