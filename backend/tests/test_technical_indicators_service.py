"""Tests for the technical-indicator service, runner, and cron endpoint."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session
from tests.fakes import FakeMarketDataProvider

from cadence.assets.category import AssetCategory
from cadence.assets.market_data import HistoryBar
from cadence.assets.models import Asset
from cadence.config import settings
from cadence.technical_indicators import constants as c
from cadence.technical_indicators import service
from cadence.technical_indicators.background import (
    TechnicalIndicatorJobRunner,
    mark_orphaned_runs_failed,
)
from cadence.technical_indicators.constants import RunPhase
from cadence.technical_indicators.models import (
    TechnicalIndicator,
    TechnicalIndicatorRun,
)


def _uptrend_bars(n: int = 320) -> list[HistoryBar]:
    start = date(2020, 1, 1)
    return [
        HistoryBar(
            date=start + timedelta(days=i), close=100.0 * (1.003**i), volume=1_000_000.0
        )
        for i in range(n)
    ]


def _add_asset(session: Session, ticker: str) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        category=AssetCategory.STOCK.value,
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


# --- service.compute_and_store / reads ------------------------------------


def test_compute_and_store_upserts_single_row(db_session: Session) -> None:
    asset = _add_asset(db_session, "AAA")
    provider = FakeMarketDataProvider(history=_uptrend_bars())

    assert service.compute_and_store(db_session, asset, provider) is True
    snap = service.get_latest_snapshot(db_session, asset.id)
    assert snap is not None
    assert snap.gate_pass is True

    # A recompute replaces the row rather than inserting a second one.
    assert service.compute_and_store(db_session, asset, provider) is True
    rows = db_session.query(TechnicalIndicator).filter_by(asset_id=asset.id).all()
    assert len(rows) == 1


def test_compute_and_store_no_history_returns_false(db_session: Session) -> None:
    asset = _add_asset(db_session, "AAA")
    provider = FakeMarketDataProvider(history=[])
    assert service.compute_and_store(db_session, asset, provider) is False
    assert service.get_latest_snapshot(db_session, asset.id) is None


def test_get_latest_snapshots_by_ids(db_session: Session) -> None:
    a = _add_asset(db_session, "AAA")
    b = _add_asset(db_session, "BBB")
    provider = FakeMarketDataProvider(history=_uptrend_bars())
    service.compute_and_store(db_session, a, provider)
    service.compute_and_store(db_session, b, provider)

    snaps = service.get_latest_snapshots(db_session, [a.id, b.id, 9999])
    assert set(snaps) == {a.id, b.id}
    assert service.get_latest_snapshots(db_session, []) == {}


# --- service.execute_run --------------------------------------------------


def test_execute_run_records_audit_and_isolates_failures(db_session: Session) -> None:
    good = _add_asset(db_session, "GOOD")
    bad = _add_asset(db_session, "BAD")
    provider = FakeMarketDataProvider(
        history=_uptrend_bars(),
        history_error_by_ticker={"BAD": RuntimeError("provider boom")},
    )
    run = service.create_run(db_session)

    result = service.execute_run(db_session, run.id, provider)

    assert result.status == RunPhase.COMPLETED.value
    assert result.assets_processed == 1
    assert result.assets_failed == 1
    assert result.started_at is not None and result.finished_at is not None
    # The good asset still stored a snapshot despite the bad one failing.
    assert service.get_latest_snapshot(db_session, good.id) is not None
    assert service.get_latest_snapshot(db_session, bad.id) is None


# --- background runner ----------------------------------------------------


def test_runner_rejects_a_second_concurrent_run(db_session: Session) -> None:
    _add_asset(db_session, "AAA")
    provider = FakeMarketDataProvider(history=_uptrend_bars())

    class _InlineExecutor:
        """Records submissions but never runs them (keeps the run 'in flight')."""

        def __init__(self) -> None:
            self.calls = 0

        def submit(self, fn: object, /, *args: object) -> object:
            self.calls += 1

            class _Pending:
                def done(self) -> bool:
                    return False

            return _Pending()

    executor = _InlineExecutor()
    runner = TechnicalIndicatorJobRunner(
        session_factory=lambda: _noop_ctx(db_session),
        provider_factory=lambda: provider,
        executor=executor,  # type: ignore[arg-type]
    )

    run1, started1 = runner.start_run(db_session)
    run2, started2 = runner.start_run(db_session)

    assert started1 is True
    assert started2 is False
    assert run2.id == run1.id
    assert executor.calls == 1


def test_mark_orphaned_runs_failed(db_session: Session) -> None:
    running = TechnicalIndicatorRun(status=RunPhase.RUNNING.value)
    db_session.add(running)
    db_session.commit()

    failed_count = mark_orphaned_runs_failed(db_session)
    assert failed_count == 1
    db_session.refresh(running)
    assert running.status == RunPhase.FAILED.value


# --- cron endpoint --------------------------------------------------------


def test_cron_endpoint_rejects_missing_token(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    resp = client.post("/api/v1/technical-indicators/runs")
    assert resp.status_code == 403


def test_cron_endpoint_rejects_wrong_token(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    resp = client.post(
        "/api/v1/technical-indicators/runs", headers={"X-Cron-Token": "wrong"}
    )
    assert resp.status_code == 403


def test_cron_endpoint_empty_token_rejects_all(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "")
    resp = client.post(
        "/api/v1/technical-indicators/runs", headers={"X-Cron-Token": ""}
    )
    assert resp.status_code == 403


def test_cron_endpoint_valid_token_starts_run(
    client, db_session: Session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    from cadence.api.routers import technical_indicators as ti_router

    provider = FakeMarketDataProvider(history=_uptrend_bars())
    started_ids: list[int] = []

    class _StubRunner:
        def start_run(self, session: Session) -> tuple[TechnicalIndicatorRun, bool]:
            run = service.create_run(session)
            started_ids.append(run.id)
            return run, True

    from cadence.api.app import app

    app.dependency_overrides[ti_router.get_technical_indicator_job_runner] = (
        lambda: _StubRunner()
    )
    try:
        resp = client.post(
            "/api/v1/technical-indicators/runs", headers={"X-Cron-Token": "secret"}
        )
    finally:
        app.dependency_overrides.pop(
            ti_router.get_technical_indicator_job_runner, None
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["started"] is True
    assert body["run_id"] in started_ids
    _ = provider


class _noop_ctx:
    """A trivial context manager that yields a pre-built session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *exc: object) -> None:
        return None


def test_get_indicator_config_reflects_constants() -> None:
    """The config projection reports the live constant values and full sets."""
    cfg = service.get_indicator_config()

    keys = {ind.key for ind in cfg.indicators}
    assert {
        "sma_50",
        "sma_200",
        "ema_20",
        "macd",
        "rsi_14",
        "roc_120",
        "obv",
        "bb_pctb",
        "bb_width",
    } <= keys
    assert len(cfg.indicators) == 17

    params = {
        ind.key: {p.name: p.value for p in ind.params} for ind in cfg.indicators
    }
    assert params["sma_50"]["period"] == c.SMA_SHORT
    assert params["sma_200"]["period"] == c.SMA_LONG
    assert params["ema_20"]["span"] == c.EMA_SPAN
    assert params["macd"] == {
        "fast": c.MACD_FAST,
        "slow": c.MACD_SLOW,
        "signal": c.MACD_SIGNAL,
    }
    assert params["rsi_14"]["period"] == c.RSI_PERIOD
    assert params["roc_120"]["period"] == c.ROC_PERIOD
    assert params["bb_pctb"] == {"period": c.BB_PERIOD, "std": c.BB_STD}

    regime_thresholds = [cond.threshold for cond in cfg.trend_gate.regime]
    assert c.SMA_SLOPE_MIN in regime_thresholds
    momentum_thresholds = [cond.threshold for cond in cfg.trend_gate.momentum]
    assert c.MACD_HIST_MIN in momentum_thresholds
    assert c.RSI_MOMENTUM_MIN in momentum_thresholds
    assert c.ROC_MOMENTUM_MIN in momentum_thresholds

    assert cfg.reversal_flags.rsi_overbought == c.RSI_OVERBOUGHT
    assert cfg.reversal_flags.slope_flatten_eps == c.SLOPE_FLATTEN_EPS
    assert {f.key for f in cfg.reversal_flags.flags} == {
        "macd_hist_rollover",
        "rsi_rollover",
        "return_decel",
        "obv_price_divergence",
        "sma200_slope_flattening",
    }
