"""API tests for the read-only technical-indicator config endpoint.

The config read is a plain, unauthenticated GET — unlike the cron-guarded
``POST /technical-indicators/runs`` — so it must succeed with no ``X-Cron-Token``
header and return the full configured setup.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import FakeMarketDataProvider

from cadence.api.schemas import TechnicalIndicatorConfig
from cadence.assets.category import AssetCategory, AssetMembership
from cadence.assets.market_data import HistoryBar
from cadence.assets.models import Asset
from cadence.technical_indicators import constants as c
from cadence.technical_indicators import service


def test_get_indicator_config_schema_validates() -> None:
    """The service projection validates cleanly against the response schema."""
    cfg = TechnicalIndicatorConfig.model_validate(service.get_indicator_config())
    assert cfg.reversal_flags.rsi_overbought == c.RSI_OVERBOUGHT
    assert cfg.reversal_flags.slope_flatten_eps == c.SLOPE_FLATTEN_EPS
    sma50 = next(i for i in cfg.indicators if i.key == "sma_50")
    assert any(p.name == "period" and p.value == c.SMA_SHORT for p in sma50.params)


def test_get_config_returns_full_config_without_cron_token(
    client: TestClient,
) -> None:
    """GET /config returns 200 with the full config and needs no cron token."""
    response = client.get("/api/v1/technical-indicators/config")
    assert response.status_code == 200

    body = response.json()
    keys = {ind["key"] for ind in body["indicators"]}
    assert {"sma_50", "sma_200", "macd", "rsi_14", "bb_pctb"} <= keys
    assert len(body["indicators"]) == 17

    gate = body["trend_gate"]
    assert gate["regime"] and gate["momentum"]
    assert gate["obv_bonus"] and gate["missing_indicator_rule"]

    flags = body["reversal_flags"]
    assert flags["rsi_overbought"] == c.RSI_OVERBOUGHT
    assert flags["slope_flatten_eps"] == c.SLOPE_FLATTEN_EPS
    assert {f["key"] for f in flags["flags"]} == {
        "macd_hist_rollover",
        "rsi_rollover",
        "return_decel",
        "obv_price_divergence",
        "sma200_slope_flattening",
    }


def test_get_config_ignores_cron_token_header(client: TestClient) -> None:
    """Supplying (or omitting) the cron token makes no difference to the read."""
    with_header = client.get(
        "/api/v1/technical-indicators/config",
        headers={"X-Cron-Token": "anything"},
    )
    assert with_header.status_code == 200


def _uptrend_bars(n: int) -> list[HistoryBar]:
    start = date(2020, 1, 1)
    return [
        HistoryBar(
            date=start + timedelta(days=i), close=100.0 * (1.003**i), volume=1_000_000.0
        )
        for i in range(n)
    ]


def _add_watchlist_asset(session: Session, ticker: str) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        category=AssetCategory.STOCK.value,
        currency="USD",
        is_eligible=True,
        membership=AssetMembership.WATCHLIST.value,
        criteria_results=[],
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def test_get_watchlist_indicators_returns_floor_and_items(
    client: TestClient, db_session: Session
) -> None:
    """GET /watchlist returns the min-bars floor and one item per watchlist asset,
    without needing a cron token."""
    asset = _add_watchlist_asset(db_session, "WLX")
    provider = FakeMarketDataProvider(history=_uptrend_bars(320))
    service.compute_and_store(db_session, asset, provider)

    response = client.get("/api/v1/technical-indicators/watchlist")
    assert response.status_code == 200

    body = response.json()
    assert body["min_bars"] == c.WATCHLIST_MIN_BARS
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["ticker"] == "WLX"
    assert item["insufficient_history"] is False
    assert item["rsi_14"] is not None
    # Long-window / trend-gate fields are not part of the watchlist payload.
    assert "gate_pass" not in item
    assert "sma_200" not in item


def test_get_watchlist_indicators_marks_insufficient_history(
    client: TestClient, db_session: Session
) -> None:
    """An asset below the bar floor is reported with the insufficient marker."""
    asset = _add_watchlist_asset(db_session, "WLY")
    short = c.WATCHLIST_MIN_BARS - 10
    provider = FakeMarketDataProvider(history=_uptrend_bars(short))
    service.compute_and_store(db_session, asset, provider)

    body = client.get("/api/v1/technical-indicators/watchlist").json()
    item = body["items"][0]
    assert item["insufficient_history"] is True
    assert item["bar_count"] == short
    assert item["rsi_14"] is None


def _add_universe_asset(session: Session, ticker: str) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        category=AssetCategory.STOCK.value,
        currency="USD",
        is_eligible=True,
        membership=AssetMembership.UNIVERSE.value,
        criteria_results=[],
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def test_get_asset_indicators_returns_universe_asset_profile(
    client: TestClient, db_session: Session
) -> None:
    """The per-asset read serves a universe asset's short-window profile (no
    trend-gate / long-window fields), with the min-bars floor, no cron token."""
    asset = _add_universe_asset(db_session, "UNV")
    provider = FakeMarketDataProvider(history=_uptrend_bars(320))
    service.compute_and_store(db_session, asset, provider)

    response = client.get("/api/v1/technical-indicators/assets/unv")
    assert response.status_code == 200

    body = response.json()
    assert body["min_bars"] == c.WATCHLIST_MIN_BARS
    indicator = body["indicator"]
    assert indicator is not None
    assert indicator["ticker"] == "UNV"
    assert indicator["insufficient_history"] is False
    assert indicator["rsi_14"] is not None
    # Long-window / trend-gate fields are not part of the per-asset payload.
    assert "gate_pass" not in indicator
    assert "sma_200" not in indicator


def test_get_asset_indicators_serves_watchlist_asset(
    client: TestClient, db_session: Session
) -> None:
    """The same per-asset read serves a watchlist asset too."""
    asset = _add_watchlist_asset(db_session, "WLZ")
    provider = FakeMarketDataProvider(history=_uptrend_bars(320))
    service.compute_and_store(db_session, asset, provider)

    indicator = client.get(
        "/api/v1/technical-indicators/assets/WLZ"
    ).json()["indicator"]
    assert indicator["ticker"] == "WLZ"
    assert indicator["insufficient_history"] is False


def test_get_asset_indicators_marks_insufficient_history(
    client: TestClient, db_session: Session
) -> None:
    """An asset below the bar floor is reported with the insufficient marker."""
    asset = _add_universe_asset(db_session, "LOW")
    short = c.WATCHLIST_MIN_BARS - 10
    provider = FakeMarketDataProvider(history=_uptrend_bars(short))
    service.compute_and_store(db_session, asset, provider)

    indicator = client.get(
        "/api/v1/technical-indicators/assets/LOW"
    ).json()["indicator"]
    assert indicator["insufficient_history"] is True
    assert indicator["bar_count"] == short
    assert indicator["rsi_14"] is None


def test_get_asset_indicators_no_snapshot_is_insufficient(
    client: TestClient, db_session: Session
) -> None:
    """An existing asset with no computed snapshot is reported as insufficient
    history (bar_count null) rather than failing."""
    _add_universe_asset(db_session, "NOSNAP")

    response = client.get("/api/v1/technical-indicators/assets/NOSNAP")
    assert response.status_code == 200
    indicator = response.json()["indicator"]
    assert indicator["insufficient_history"] is True
    assert indicator["bar_count"] is None
    assert indicator["rsi_14"] is None


def test_get_asset_indicators_unknown_ticker_returns_404(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/technical-indicators/assets/GHOST")
    assert response.status_code == 404
