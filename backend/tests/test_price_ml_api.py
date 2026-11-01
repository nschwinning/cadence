"""Cron-guarded price-ML precompute endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.test_price_ml_service import _asset_with_history

from cadence.config import settings
from cadence.price_ml.models import PriceMlSignal


def test_refresh_rejects_without_token(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    resp = client.post("/api/v1/price-ml/refresh")
    assert resp.status_code == 403


def test_refresh_rejects_wrong_token(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    resp = client.post(
        "/api/v1/price-ml/refresh", headers={"X-Cron-Token": "wrong"}
    )
    assert resp.status_code == 403


def test_refresh_empty_config_rejects_all(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "")
    resp = client.post("/api/v1/price-ml/refresh", headers={"X-Cron-Token": ""})
    assert resp.status_code == 403


def test_refresh_runs_with_valid_token(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    monkeypatch.setattr(settings, "PRICE_ML_MODEL_DIR", str(tmp_path))
    _asset_with_history(db_session, "AAA", seed=1)
    _asset_with_history(db_session, "BBB", seed=2)

    resp = client.post(
        "/api/v1/price-ml/refresh", headers={"X-Cron-Token": "secret"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assets_processed"] == 2
    assert body["model_version"] == settings.PRICE_ML_MODEL_VERSION

    stored = db_session.execute(
        select(func.count()).select_from(PriceMlSignal)
    ).scalar_one()
    assert stored == 2
