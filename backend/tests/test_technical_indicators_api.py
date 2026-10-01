"""API tests for the read-only technical-indicator config endpoint.

The config read is a plain, unauthenticated GET — unlike the cron-guarded
``POST /technical-indicators/runs`` — so it must succeed with no ``X-Cron-Token``
header and return the full configured setup.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from cadence.api.schemas import TechnicalIndicatorConfig
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
