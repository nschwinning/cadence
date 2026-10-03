"""Tests for the range-scoped dashboard overview (service + HTTP).

The overview aggregates over active paper-trading sessions: per-session value
series windowed to the range, range-relative pnl/fees, the AI-automation summary,
the recent-activity feed, the range-independent universe balance, and best/worst
performers from stored price history. These tests seed snapshots, trades, AI
events, and price history directly so each range window is deterministic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import FakeBroker, FakeMarketDataProvider

from cadence.ai_portfolio.constants import EventStatus, EventType
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.assets import service as assets_service
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.broker.stub import StubBroker
from cadence.dashboard import service
from cadence.dashboard.constants import RECENT_ACTIVITY_LIMIT, DashboardRange
from cadence.paper_trading import service as paper_trading_service
from cadence.paper_trading.constants import Benchmark, SessionStatus
from cadence.paper_trading.models import (
    PaperTrade,
    PaperTradingSession,
    SessionValueSnapshot,
)
from cadence.portfolios import service as portfolios_service
from cadence.price_history import service as price_history_service

_TODAY = date(2026, 6, 15)
_NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def _broker() -> FakeBroker:
    return FakeBroker()


def _provider(
    *,
    quote_type: str = "EQUITY",
    sector_key: str | None = "technology",
    country: str | None = "USA",
    market_cap: float = 5_000_000_000.0,
) -> FakeMarketDataProvider:
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Co",
            exchange="NASDAQ",
            currency="USD",
            price=50.0,
            market_cap=market_cap,
            quote_type=quote_type,
            sector_key=sector_key,
            country=country,
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def _make_session(
    db_session: Session,
    *,
    name: str,
    strategy_key: str,
    allocated: float = 10_000.0,
) -> PaperTradingSession:
    portfolio = portfolios_service.create_portfolio(
        db_session, name=name, stocks=["TECH"]
    )
    return paper_trading_service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key=strategy_key,
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
        allocated_capital=allocated,
        benchmark=Benchmark.SP500,
    )


def _add_snapshot(
    db_session: Session,
    session_id: uuid.UUID,
    *,
    on: date,
    total_value: float,
) -> None:
    db_session.add(
        SessionValueSnapshot(
            session_id=session_id,
            snapshot_date=on,
            total_value=total_value,
            cash_value=total_value,
            positions_value=0.0,
            daily_pnl=0.0,
            daily_pnl_pct=0.0,
            positions=[],
        )
    )
    db_session.flush()


def _add_trade(
    db_session: Session, session_id: uuid.UUID, *, executed_at: datetime
) -> None:
    db_session.add(
        PaperTrade(
            session_id=session_id,
            ticker="TECH",
            side="buy",
            quantity=1.0,
            price=10.0,
            notional=10.0,
            signal_type="entry",
            executed_at=executed_at,
        )
    )
    db_session.flush()


def _add_event(
    db_session: Session,
    *,
    event_type: EventType,
    status: EventStatus,
    created_at: datetime,
    session_id: uuid.UUID | None = None,
) -> AIPortfolioEvent:
    event = AIPortfolioEvent(
        session_id=session_id,
        event_type=event_type.value,
        status=status.value,
        created_at=created_at,
    )
    db_session.add(event)
    db_session.flush()
    return event


# --- empty system -----------------------------------------------------------


def test_overview_empty_system_is_zeroed(db_session: Session) -> None:
    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    assert overview.sessions == []
    assert overview.recent_activity == []
    assert overview.universe_performers.best == []
    assert overview.universe_performers.worst == []
    assert overview.universe_balance.total == 0
    assert overview.universe_balance.top_sector_key is None
    assert overview.universe_balance.top_sector_share == 0.0
    assert overview.automation.latest_run is None
    assert overview.automation.in_flight is False
    assert overview.automation.failed_in_range == 0
    assert overview.automation.next_run_is_approximate is True


# --- per-session performance ------------------------------------------------


def test_session_series_windowed_and_range_relative_pnl(db_session: Session) -> None:
    session_row = _make_session(
        db_session, name="Alpha", strategy_key="s1", allocated=10_000.0
    )
    # One snapshot before the 1M window start (today-30 = 2026-05-16), one inside.
    _add_snapshot(db_session, session_row.id, on=date(2026, 5, 1), total_value=9_000.0)
    _add_snapshot(db_session, session_row.id, on=date(2026, 6, 5), total_value=11_000.0)

    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    assert len(overview.sessions) == 1
    perf = overview.sessions[0]
    assert perf.label == "Alpha"
    assert perf.allocated_capital == 10_000.0
    # No open positions/pnl/fees -> current value equals allocated capital.
    assert perf.current_value == 10_000.0
    # Series is windowed to the range: the pre-window snapshot is dropped.
    assert [p.date for p in perf.points] == [date(2026, 6, 5)]
    # Range pnl = current value - value at the range start (the 9_000 snapshot).
    assert perf.pnl == 1_000.0


def test_session_starting_within_range_baselines_on_allocated(
    db_session: Session,
) -> None:
    session_row = _make_session(
        db_session, name="Beta", strategy_key="s2", allocated=10_000.0
    )
    # Only snapshot is inside the window -> no value before the range start.
    _add_snapshot(db_session, session_row.id, on=date(2026, 6, 10), total_value=12_000.0)

    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    perf = overview.sessions[0]
    assert [p.date for p in perf.points] == [date(2026, 6, 10)]
    # Baselines on allocated capital (current value - allocated).
    assert perf.pnl == 0.0


def test_range_fees_count_trades_within_window(db_session: Session) -> None:
    session_row = _make_session(db_session, name="Gamma", strategy_key="s3")
    # Two trades inside the 1M window, one before it.
    _add_trade(db_session, session_row.id, executed_at=datetime(2026, 5, 1, tzinfo=UTC))
    _add_trade(db_session, session_row.id, executed_at=datetime(2026, 6, 1, tzinfo=UTC))
    _add_trade(db_session, session_row.id, executed_at=datetime(2026, 6, 10, tzinfo=UTC))

    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    # Flat $1/trade transaction cost; only the two in-window trades count.
    assert overview.sessions[0].fees == 2.0


def test_only_active_sessions_are_included(db_session: Session) -> None:
    active = _make_session(db_session, name="Active", strategy_key="a")
    closed = _make_session(db_session, name="Closed", strategy_key="c")
    paper_trading_service.update_session_status(
        db_session, closed.id, SessionStatus.STOPPED
    )

    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    assert [p.id for p in overview.sessions] == [active.id]


# --- automation summary -----------------------------------------------------


def test_automation_summary_reports_each_field(db_session: Session) -> None:
    session_row = _make_session(db_session, name="Auto", strategy_key="auto")
    # Latest rebalance run (newest) and an older one.
    _add_event(
        db_session,
        event_type=EventType.REBALANCE,
        status=EventStatus.SUCCEEDED,
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    latest = _add_event(
        db_session,
        event_type=EventType.REBALANCE,
        status=EventStatus.PARTIAL,
        created_at=datetime(2026, 6, 10, tzinfo=UTC),
    )
    # A failed run inside the range and one before it.
    _add_event(
        db_session,
        event_type=EventType.REBALANCE,
        status=EventStatus.FAILED,
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    _add_event(
        db_session,
        event_type=EventType.REBALANCE,
        status=EventStatus.FAILED,
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    # An in-flight rebalance tied to the active session (older than the latest run
    # so the "latest" assertion still points at the PARTIAL run).
    _add_event(
        db_session,
        event_type=EventType.REBALANCE,
        status=EventStatus.RUNNING,
        created_at=datetime(2026, 6, 5, tzinfo=UTC),
        session_id=session_row.id,
    )

    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    automation = overview.automation
    assert automation.latest_run is not None
    assert automation.latest_run.id == latest.id
    assert automation.latest_run.status == EventStatus.PARTIAL.value
    assert automation.in_flight is True
    # Only the in-range failed run counts (the January one is outside 1M).
    assert automation.failed_in_range == 1
    # Next run is the same-day 16:15 ET slot (after the 12:00 UTC = 08:00 ET now).
    assert automation.next_run_approx > _NOW
    assert automation.next_run_is_approximate is True


# --- recent activity --------------------------------------------------------


def test_recent_activity_ordered_capped_and_labeled(db_session: Session) -> None:
    session_row = _make_session(db_session, name="Feed", strategy_key="feed")
    # One event outside the range (must be excluded).
    _add_event(
        db_session,
        event_type=EventType.BUILD,
        status=EventStatus.SUCCEEDED,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        session_id=session_row.id,
    )
    # More in-range events than the cap, ascending in time.
    for i in range(RECENT_ACTIVITY_LIMIT + 3):
        _add_event(
            db_session,
            event_type=EventType.REBALANCE,
            status=EventStatus.SUCCEEDED,
            created_at=datetime(2026, 6, 1, tzinfo=UTC) + timedelta(hours=i),
            session_id=session_row.id,
        )

    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    activity = overview.recent_activity
    assert len(activity) == RECENT_ACTIVITY_LIMIT
    # Newest first.
    times = [entry.created_at for entry in activity]
    assert times == sorted(times, reverse=True)
    # Session label resolved from the portfolio name.
    assert activity[0].session_label == "Feed"
    assert activity[0].kind == EventType.REBALANCE.value


# --- universe balance & performers ------------------------------------------


def _seed_assets(db_session: Session) -> dict[str, int]:
    """Seed TECH + FIN (eligible) and BTC-USD (crypto, no sector); return ids."""
    ids: dict[str, int] = {}
    tech = assets_service.add_asset(
        db_session, "TECH", _provider(sector_key="technology"), _broker()
    )
    fin = assets_service.add_asset(
        db_session, "FIN", _provider(sector_key="financial-services"), _broker()
    )
    btc = assets_service.add_asset(
        db_session,
        "BTC-USD",
        _provider(quote_type="CRYPTOCURRENCY", sector_key=None),
        _broker(),
    )
    ids["TECH"] = tech.id
    ids["FIN"] = fin.id
    ids["BTC-USD"] = btc.id
    return ids


def test_universe_balance_reflects_current_composition(db_session: Session) -> None:
    _seed_assets(db_session)

    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    balance = overview.universe_balance
    assert balance.total == 3
    assert balance.eligible == 3
    assert balance.ineligible == 0
    # technology, financial-services, and the "no sector" bucket for crypto.
    assert balance.sectors_count == 3
    assert balance.top_category_key == "stock"
    assert balance.top_category_share == 2 / 3


def test_universe_balance_is_range_independent(db_session: Session) -> None:
    _seed_assets(db_session)

    month = service.get_dashboard_overview(
        db_session, range_=DashboardRange.MONTH, broker=StubBroker(), today=_TODAY
    )
    year = service.get_dashboard_overview(
        db_session, range_=DashboardRange.YEAR, broker=StubBroker(), today=_TODAY
    )

    assert month.universe_balance == year.universe_balance


def test_performers_ranked_and_exclude_insufficient_history(
    db_session: Session,
) -> None:
    ids = _seed_assets(db_session)
    # TECH: +20% over the window; FIN: -10%; BTC-USD: only one close -> excluded.
    price_history_service.store_closes(
        db_session,
        ids["TECH"],
        [(date(2026, 6, 1), 100.0), (date(2026, 6, 10), 120.0)],
    )
    price_history_service.store_closes(
        db_session,
        ids["FIN"],
        [(date(2026, 6, 1), 100.0), (date(2026, 6, 10), 90.0)],
    )
    price_history_service.store_closes(
        db_session, ids["BTC-USD"], [(date(2026, 6, 10), 100.0)]
    )
    db_session.flush()

    overview = service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MONTH,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    performers = overview.universe_performers
    best_tickers = [e.ticker for e in performers.best]
    worst_tickers = [e.ticker for e in performers.worst]
    # Only TECH and FIN have enough history; BTC-USD is excluded.
    assert best_tickers == ["TECH", "FIN"]
    assert worst_tickers == ["FIN", "TECH"]
    assert performers.best[0].ticker == "TECH"
    assert abs(performers.best[0].return_pct - 0.2) < 1e-9


# --- HTTP layer -------------------------------------------------------------


def test_overview_endpoint_returns_payload(
    client: TestClient, db_session: Session
) -> None:
    _make_session(db_session, name="Alpha", strategy_key="s1")

    response = client.get("/api/v1/dashboard/overview", params={"range": "1M"})

    assert response.status_code == 200
    body = response.json()
    assert body["range"] == "1M"
    assert isinstance(body["sessions"], list)
    assert "automation" in body
    assert "universe_balance" in body
    assert "universe_performers" in body


def test_overview_endpoint_rejects_unsupported_range(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/overview", params={"range": "7D"})

    assert response.status_code == 422


def test_overview_endpoint_requires_range(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/overview")

    assert response.status_code == 422
