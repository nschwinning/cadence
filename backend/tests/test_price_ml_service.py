"""Precompute, storage, and staleness-aware read tests for the price-ML service."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.test_price_ml_features import _synthetic_closes

from cadence.assets.models import Asset
from cadence.price_history.models import PriceHistory
from cadence.price_ml import service
from cadence.price_ml.constants import SignalDirection, SignalStatus
from cadence.price_ml.models import PriceMlSignal


def _asset_with_history(
    db_session: Session, ticker: str, *, n: int = 320, seed: int = 1
) -> Asset:
    asset = Asset(
        ticker=ticker,
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.flush()
    rows = [
        PriceHistory(asset_id=asset.id, date=d, close=c)
        for d, c in _synthetic_closes(n, seed=seed)
    ]
    db_session.add_all(rows)
    db_session.flush()
    return asset


def _signal_count(db_session: Session, asset_id: int) -> int:
    return db_session.execute(
        select(func.count())
        .select_from(PriceMlSignal)
        .where(PriceMlSignal.asset_id == asset_id)
    ).scalar_one()


# --- precompute -------------------------------------------------------------


def test_refresh_records_one_row_per_asset_and_replaces(
    db_session: Session, tmp_path
) -> None:
    a = _asset_with_history(db_session, "AAA", seed=1)
    b = _asset_with_history(db_session, "BBB", seed=2)

    first = service.refresh_signals(
        db_session, today=date(2024, 6, 1), model_dir=str(tmp_path)
    )
    assert first.assets_processed == 2
    assert first.assets_failed == 0
    assert _signal_count(db_session, a.id) == 1
    assert _signal_count(db_session, b.id) == 1

    # A second run replaces each asset's row rather than appending.
    second = service.refresh_signals(
        db_session, today=date(2024, 6, 2), model_dir=str(tmp_path)
    )
    assert second.assets_processed == 2
    assert _signal_count(db_session, a.id) == 1
    assert _signal_count(db_session, b.id) == 1

    signal = service.get_latest_ml_signal(db_session, a.id)
    assert signal is not None
    assert signal.direction in {SignalDirection.UP.value, SignalDirection.DOWN.value}
    assert 0.0 <= signal.probability <= 1.0
    assert signal.as_of_date == date(2024, 6, 2)


def test_refresh_isolates_per_asset_failures(
    db_session: Session, tmp_path, monkeypatch
) -> None:
    _asset_with_history(db_session, "AAA", seed=1)
    _asset_with_history(db_session, "BBB", seed=2)

    real = service.features.latest_feature_row
    calls = {"n": 0}

    def flaky(closes):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(closes)

    monkeypatch.setattr(service.features, "latest_feature_row", flaky)

    summary = service.refresh_signals(
        db_session, today=date(2024, 6, 1), model_dir=str(tmp_path)
    )
    assert summary.assets_failed == 1
    assert summary.assets_processed == 1
    total = db_session.execute(
        select(func.count()).select_from(PriceMlSignal)
    ).scalar_one()
    assert total == 1


def test_refresh_skips_assets_below_min_bar_count(
    db_session: Session, tmp_path
) -> None:
    _asset_with_history(db_session, "AAA", seed=1)  # 320 bars, eligible
    _asset_with_history(db_session, "TINY", n=50, seed=3)  # below 260

    summary = service.refresh_signals(
        db_session, today=date(2024, 6, 1), model_dir=str(tmp_path)
    )
    assert summary.assets_skipped >= 1
    assert summary.assets_processed == 1


def test_refresh_empty_universe(db_session: Session, tmp_path) -> None:
    summary = service.refresh_signals(
        db_session, today=date(2024, 6, 1), model_dir=str(tmp_path)
    )
    assert summary.assets_processed == 0
    assert summary.assets_failed == 0
    assert summary.trained is False


# --- reads ------------------------------------------------------------------


def _record(db_session: Session, asset_id: int, *, as_of: date) -> PriceMlSignal:
    return service.record_signal(
        db_session,
        asset_id=asset_id,
        as_of_date=as_of,
        horizon_days=21,
        direction=SignalDirection.UP.value,
        probability=0.63,
        recent_oos_accuracy=0.55,
        model_version="price-ml-v1",
        feature_as_of=as_of,
        bar_count=300,
    )


def test_get_latest_ml_signals_omits_assets_without_signal(
    db_session: Session,
) -> None:
    a = _asset_with_history(db_session, "AAA", seed=1)
    b = _asset_with_history(db_session, "BBB", seed=2)
    _record(db_session, a.id, as_of=date(2024, 6, 1))

    signals = service.get_latest_ml_signals(db_session, [a.id, b.id])
    assert set(signals) == {a.id}
    assert service.get_latest_ml_signals(db_session, []) == {}


def test_signal_annotation_available() -> None:
    signal = PriceMlSignal(
        asset_id=1,
        as_of_date=date(2024, 6, 1),
        horizon_days=21,
        direction=SignalDirection.UP.value,
        probability=0.631234,
        recent_oos_accuracy=0.554321,
        model_version="price-ml-v1",
        feature_as_of=date(2024, 6, 1),
        bar_count=300,
    )
    block = service.signal_annotation(
        signal, as_of=date(2024, 6, 3), staleness_days=7
    )
    assert block["status"] == SignalStatus.AVAILABLE.value
    assert block["direction"] == SignalDirection.UP.value
    assert block["probability"] == 0.6312
    assert block["recent_oos_accuracy"] == 0.5543
    assert block["as_of"] == "2024-06-01"
    assert block["horizon_days"] == 21


def test_signal_annotation_missing_is_unavailable() -> None:
    block = service.signal_annotation(None, as_of=date(2024, 6, 1), staleness_days=7)
    assert block == {"status": SignalStatus.UNAVAILABLE.value}


def test_signal_annotation_stale_is_unavailable() -> None:
    signal = PriceMlSignal(
        asset_id=1,
        as_of_date=date(2024, 6, 1),
        horizon_days=21,
        direction=SignalDirection.UP.value,
        probability=0.6,
        recent_oos_accuracy=None,
        model_version="price-ml-v1",
        feature_as_of=date(2024, 6, 1),
        bar_count=300,
    )
    block = service.signal_annotation(
        signal, as_of=date(2024, 6, 1) + timedelta(days=8), staleness_days=7
    )
    assert block == {"status": SignalStatus.UNAVAILABLE.value}


def test_resolve_signal_annotations_maps_by_ticker(db_session: Session) -> None:
    a = _asset_with_history(db_session, "AAA", seed=1)
    b = _asset_with_history(db_session, "BBB", seed=2)
    _record(db_session, a.id, as_of=date(2024, 6, 1))

    result = service.resolve_signal_annotations(
        db_session,
        {"AAA": a.id, "BBB": b.id},
        as_of=date(2024, 6, 3),
        staleness_days=7,
    )
    assert result["AAA"]["status"] == SignalStatus.AVAILABLE.value
    assert result["BBB"] == {"status": SignalStatus.UNAVAILABLE.value}
