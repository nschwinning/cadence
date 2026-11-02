"""Unit tests for the strategy-bot session service, tick runner, and KPIs."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.broker.stub import StubBroker
from cadence.strategy_bots import service
from cadence.strategy_bots.errors import (
    BotSessionNotArchivableError,
    IneligibleAssetError,
    InvalidBotBenchmarkError,
    UnknownStrategyError,
)
from cadence.strategy_bots.market_data import BarsResult, StubMarketData
from cadence.strategy_bots.models import BotSession
from cadence.strategy_bots.strategy import Bar

_NOW = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
_PARAMS = {"fast_period": 2, "slow_period": 3}


def _add_asset(
    db_session: Session,
    ticker: str = "AAPL",
    *,
    category: str = "stock",
    is_eligible: bool = True,
) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category=category,
        currency="USD",
        is_eligible=is_eligible,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.flush()
    return asset


class _OpenableBroker(StubBroker):
    """StubBroker with a toggleable market-open state."""

    def __init__(self, *, market_open: bool = True) -> None:
        super().__init__()
        self._market_open = market_open

    def is_market_open(self) -> bool:
        return self._market_open


class _FixedMarketData:
    """Returns a preset bar series and freshness, ignoring the request args."""

    def __init__(self, closes: list[float], *, fresh: bool = True) -> None:
        self._closes = closes
        self._fresh = fresh

    def latest_bars(
        self, symbol: str, timeframe: str, count: int, *, now: datetime
    ) -> BarsResult:
        bars = [
            Bar(
                timestamp=now,
                open=c,
                high=c,
                low=c,
                close=c,
                volume=1000.0,
            )
            for c in self._closes
        ]
        as_of = bars[-1].timestamp if bars else None
        return BarsResult(bars=bars, as_of=as_of, fresh=self._fresh)


def _create(db_session: Session, **overrides: object) -> BotSession:
    kwargs: dict[str, object] = {
        "strategy_key": "ma_crossover",
        "ticker": "AAPL",
        "initial_capital": 100_000.0,
        "benchmark": "SP500",
        "strategy_params": dict(_PARAMS),
    }
    kwargs.update(overrides)
    return service.create_bot_session(db_session, **kwargs)  # type: ignore[arg-type]


# Lifecycle ---------------------------------------------------------------
def test_create_bot_session_persists_active(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    assert bot.id is not None
    assert bot.status == "active"
    assert bot.ticker == "AAPL"
    assert bot.benchmark == "SP500"
    assert bot.allocated_capital == 100_000.0
    assert bot.peak_value == 100_000.0
    assert bot.strategy_params["slow_period"] == 3


def test_create_rejects_unknown_strategy(db_session: Session) -> None:
    _add_asset(db_session)
    with pytest.raises(UnknownStrategyError):
        _create(db_session, strategy_key="not_a_strategy")


def test_create_rejects_unknown_benchmark(db_session: Session) -> None:
    _add_asset(db_session)
    with pytest.raises(InvalidBotBenchmarkError):
        _create(db_session, benchmark="NOT_A_BENCHMARK")


def test_create_rejects_non_universe_ticker(db_session: Session) -> None:
    # No asset inserted for ZZZZ.
    with pytest.raises(IneligibleAssetError):
        _create(db_session, ticker="ZZZZ")


def test_create_rejects_non_equity_asset(db_session: Session) -> None:
    _add_asset(db_session, ticker="BTC", category="crypto")
    with pytest.raises(IneligibleAssetError):
        _create(db_session, ticker="BTC")


def test_create_rejects_ineligible_asset(db_session: Session) -> None:
    _add_asset(db_session, ticker="PENNY", is_eligible=False)
    with pytest.raises(IneligibleAssetError):
        _create(db_session, ticker="PENNY")


def test_stop_then_archive_transitions(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    service.stop_bot_session(db_session, bot.id)
    assert bot.status == "stopped"

    service.archive_bot_session(db_session, bot.id)
    assert bot.status == "archived"
    assert bot.archived_at is not None


def test_archive_requires_stopped(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    with pytest.raises(BotSessionNotArchivableError):
        service.archive_bot_session(db_session, bot.id)


def test_list_hides_archived_by_default(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.stop_bot_session(db_session, bot.id)
    service.archive_bot_session(db_session, bot.id)

    assert service.list_bot_sessions(db_session) == []
    assert len(service.list_bot_sessions(db_session, include_archived=True)) == 1


# Tick runner -------------------------------------------------------------
def test_tick_market_closed_is_noop(db_session: Session) -> None:
    _add_asset(db_session)
    _create(db_session)
    broker = _OpenableBroker(market_open=False)

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=StubMarketData(),
        now=_NOW,
    )

    assert result.market_open is False
    assert result.processed == 0


def test_tick_only_advances_active_sessions(db_session: Session) -> None:
    _add_asset(db_session)
    active = _create(db_session)
    stopped = _create(db_session)
    service.stop_bot_session(db_session, stopped.id)
    broker = _OpenableBroker()

    # Flat series -> HOLD, no orders, but the active session is processed.
    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_FixedMarketData([10.0, 10.0, 10.0, 10.0]),
        now=_NOW,
    )

    assert result.processed == 1
    assert active.total_trades == 0


def test_tick_full_recompute_enters_on_up_cross(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    broker = _OpenableBroker()
    price = broker.get_quote("AAPL").last
    assert price is not None
    # Flat then a jump to the broker's fill price -> fast SMA crosses above slow,
    # and the final close equals the fill price so sizing matches the fill.
    closes = [price * 0.5, price * 0.5, price * 0.5, price * 0.5, price]

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_FixedMarketData(closes),
        now=_NOW,
    )

    assert result.processed == 1
    assert bot.position_qty is not None and bot.position_qty > 0
    assert bot.total_trades == 1
    assert bot.trades[0].side == "buy"


def test_tick_skips_session_when_data_stale(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    broker = _OpenableBroker()

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_FixedMarketData([10.0, 10.0, 10.0, 10.0], fresh=False),
        now=_NOW,
    )

    assert result.skipped == 1
    assert result.processed == 0
    assert bot.is_flat
    assert bot.total_trades == 0


# Snapshots & KPIs --------------------------------------------------------
def test_record_snapshot_and_upsert(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    when = date(2026, 1, 5)

    snap = service.record_bot_snapshot(db_session, bot, price=0.0, snapshot_date=when)
    assert snap.total_value == 100_000.0  # flat: cash only
    assert snap.unrealised_pnl == 0.0

    # Re-recording the same day updates in place (no duplicate row).
    again = service.record_bot_snapshot(
        db_session, bot, price=0.0, snapshot_date=when
    )
    assert again.id == snap.id
    assert len(service.list_bot_snapshots(db_session, bot)) == 1


def test_snapshot_marks_open_position_to_market(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    bot.position_qty = 100.0
    bot.position_avg_price = 50.0
    db_session.flush()

    snap = service.record_bot_snapshot(
        db_session, bot, price=60.0, snapshot_date=date(2026, 1, 6)
    )
    # 100 shares * (60 - 50) = +1000 unrealised on top of the 100k basis.
    assert snap.unrealised_pnl == pytest.approx(1000.0)
    assert snap.total_value == pytest.approx(101_000.0)


def test_kpis_from_snapshots(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.record_bot_snapshot(
        db_session, bot, price=0.0, snapshot_date=date(2026, 1, 5)
    )
    bot.position_qty = 100.0
    bot.position_avg_price = 50.0
    db_session.flush()
    service.record_bot_snapshot(
        db_session, bot, price=60.0, snapshot_date=date(2026, 1, 6)
    )

    kpis = service.bot_session_kpis(db_session, bot)
    assert kpis.current_value == pytest.approx(101_000.0)
    assert kpis.unrealised_pnl == pytest.approx(1000.0)
    assert kpis.total_return == pytest.approx(1000.0)
    assert kpis.total_return_pct == pytest.approx(0.01)


def test_kpis_without_snapshots_fall_back_to_cash(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    kpis = service.bot_session_kpis(db_session, bot)
    assert kpis.current_value == 100_000.0
    assert kpis.total_return == 0.0
    assert kpis.max_drawdown == 0.0
