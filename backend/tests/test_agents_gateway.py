"""Unit tests for the opt-in LiteLLM model-gateway seam.

No network calls: the SDK client-registration functions are patched, and
``run_config_for_trace`` is pure.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from pytest import MonkeyPatch

from cadence.agents import gateway
from cadence.config import settings


def _enable(monkeypatch: MonkeyPatch, url: str = "http://litellm:4000") -> None:
    monkeypatch.setattr(settings, "LITELLM_BASE_URL", url)


def _disable(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LITELLM_BASE_URL", "")


# --------------------------------------------------------------------------- #
# configure_model_gateway
# --------------------------------------------------------------------------- #


def test_configure_is_noop_when_disabled(monkeypatch: MonkeyPatch) -> None:
    _disable(monkeypatch)
    set_client = Mock()
    set_tracing = Mock()
    monkeypatch.setattr(gateway, "set_default_openai_client", set_client)
    monkeypatch.setattr(gateway, "set_tracing_disabled", set_tracing)

    assert gateway.configure_model_gateway() is False
    set_client.assert_not_called()
    set_tracing.assert_not_called()


def test_configure_registers_client_once_when_enabled(monkeypatch: MonkeyPatch) -> None:
    _enable(monkeypatch)
    set_client = Mock()
    set_tracing = Mock()
    async_openai = Mock(return_value="client")
    monkeypatch.setattr(gateway, "set_default_openai_client", set_client)
    monkeypatch.setattr(gateway, "set_tracing_disabled", set_tracing)
    monkeypatch.setattr(gateway, "AsyncOpenAI", async_openai)

    assert gateway.configure_model_gateway() is True
    set_client.assert_called_once_with("client")
    set_tracing.assert_called_once_with(True)
    # Client points at the configured proxy base URL.
    assert async_openai.call_args.kwargs["base_url"] == "http://litellm:4000"


# --------------------------------------------------------------------------- #
# run_config_for_trace + llm_trace
# --------------------------------------------------------------------------- #


def test_run_config_none_when_disabled(monkeypatch: MonkeyPatch) -> None:
    _disable(monkeypatch)
    with gateway.llm_trace("evt-1"):
        assert gateway.run_config_for_trace() is None


def test_run_config_none_without_trace(monkeypatch: MonkeyPatch) -> None:
    _enable(monkeypatch)
    assert gateway.run_config_for_trace() is None


def test_run_config_carries_trace_id(monkeypatch: MonkeyPatch) -> None:
    _enable(monkeypatch)
    with gateway.llm_trace("evt-123"):
        config = gateway.run_config_for_trace()

    assert config is not None
    # The trace id rides in the LiteLLM spend-log metadata header as JSON — the
    # only mechanism LiteLLM persists for Responses-API runs (verified live).
    headers = config.model_settings.extra_headers
    assert headers is not None
    assert set(headers) == {"x-litellm-spend-logs-metadata"}
    assert json.loads(headers["x-litellm-spend-logs-metadata"]) == {
        "cadence_trace_id": "evt-123"
    }


def test_run_config_carries_session_and_portfolio(monkeypatch: MonkeyPatch) -> None:
    _enable(monkeypatch)
    with gateway.llm_trace("evt-9", session_id="sess-7", portfolio_id="pf-3"):
        config = gateway.run_config_for_trace()

    assert config is not None
    headers = config.model_settings.extra_headers
    assert headers is not None
    # Portfolio-scoped runs attribute spend to the session + portfolio.
    assert json.loads(headers["x-litellm-spend-logs-metadata"]) == {
        "cadence_trace_id": "evt-9",
        "cadence_session_id": "sess-7",
        "cadence_portfolio_id": "pf-3",
    }


def test_run_config_trace_only_without_session(monkeypatch: MonkeyPatch) -> None:
    # Global runs (recommender / universe-eval) pass neither session nor portfolio,
    # so their spend carries only the trace id — never a session/portfolio id.
    _enable(monkeypatch)
    with gateway.llm_trace("recommendation-run-1"):
        config = gateway.run_config_for_trace()

    assert config is not None
    headers = config.model_settings.extra_headers
    assert headers is not None
    payload = json.loads(headers["x-litellm-spend-logs-metadata"])
    assert payload == {"cadence_trace_id": "recommendation-run-1"}
    assert "cadence_session_id" not in payload
    assert "cadence_portfolio_id" not in payload


def test_llm_trace_resets_after_block(monkeypatch: MonkeyPatch) -> None:
    _enable(monkeypatch)
    with gateway.llm_trace("evt-a"):
        pass
    # Outside the block the trace id is cleared, so no config is produced.
    assert gateway.run_config_for_trace() is None


@pytest.mark.parametrize("url", ["", "   "])
def test_gateway_enabled_false_for_blank(monkeypatch: MonkeyPatch, url: str) -> None:
    monkeypatch.setattr(settings, "LITELLM_BASE_URL", url)
    assert gateway.gateway_enabled() is False
