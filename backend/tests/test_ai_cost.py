"""Unit tests for the best-effort LiteLLM per-session AI-cost read helper."""

from __future__ import annotations

from typing import Any, Self

from pytest import MonkeyPatch

from cadence.config import settings
from cadence.paper_trading import ai_cost


class _FakeConn:
    def __init__(self, scalar: float | None) -> None:
        self._scalar = scalar

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, *args: Any, **kwargs: Any) -> _FakeConn:
        return self

    def scalar(self) -> float | None:
        return self._scalar


class _FakeEngine:
    def __init__(self, scalar: float | None) -> None:
        self._scalar = scalar

    def connect(self) -> _FakeConn:
        return _FakeConn(self._scalar)


def _never_called(url: str) -> Any:
    raise AssertionError("_spend_engine must not be called when the URL is unset")


def test_cost_is_none_when_url_unset(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "")
    # The DB is never touched when disabled: the engine factory is never called.
    monkeypatch.setattr(ai_cost, "_spend_engine", _never_called)
    assert ai_cost.session_ai_cost_usd("sess-1") is None


def test_cost_sums_spend_when_configured(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "postgresql://u:p@h:5432/litellm")
    monkeypatch.setattr(ai_cost, "_spend_engine", lambda url: _FakeEngine(12.34))
    assert ai_cost.session_ai_cost_usd("sess-1") == 12.34


def test_cost_is_none_when_no_spend(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "postgresql://u:p@h:5432/litellm")
    monkeypatch.setattr(ai_cost, "_spend_engine", lambda url: _FakeEngine(None))
    assert ai_cost.session_ai_cost_usd("sess-1") is None


def test_cost_is_none_on_read_error(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "postgresql://u:p@h:5432/litellm")

    def _boom(url: str) -> _FakeEngine:
        raise ConnectionError("spend table unreachable")

    monkeypatch.setattr(ai_cost, "_spend_engine", _boom)
    # Best-effort: a read failure yields None rather than propagating.
    assert ai_cost.session_ai_cost_usd("sess-1") is None
