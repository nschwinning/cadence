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


class _FakeRowsConn:
    """Connection stub for the batched helper: captures params, returns rows."""

    def __init__(self, rows: list[tuple[str | None, float | None]]) -> None:
        self._rows = rows
        self.params: dict[str, Any] | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, _query: Any, params: dict[str, Any]) -> _FakeRowsConn:
        self.params = params
        return self

    def all(self) -> list[tuple[str | None, float | None]]:
        return self._rows


class _FakeRowsEngine:
    def __init__(self, conn: _FakeRowsConn) -> None:
        self._conn = conn

    def connect(self) -> _FakeRowsConn:
        return self._conn


def test_costs_empty_ids_short_circuits(monkeypatch: MonkeyPatch) -> None:
    # An empty id list never touches the DB and returns an empty map.
    monkeypatch.setattr(ai_cost, "_spend_engine", _never_called)
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "postgresql://u:p@h:5432/litellm")
    assert ai_cost.session_ai_costs_usd([]) == {}


def test_costs_none_when_url_unset(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "")
    monkeypatch.setattr(ai_cost, "_spend_engine", _never_called)
    assert ai_cost.session_ai_costs_usd(["sess-1"]) is None


def test_costs_group_maps_sessions(monkeypatch: MonkeyPatch) -> None:
    conn = _FakeRowsConn([("sess-1", 12.34), ("sess-2", 5.0)])
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "postgresql://u:p@h:5432/litellm")
    monkeypatch.setattr(ai_cost, "_spend_engine", lambda url: _FakeRowsEngine(conn))
    result = ai_cost.session_ai_costs_usd(["sess-1", "sess-2", "sess-3"])
    # Session absent from the grouped rows (no spend) is simply not in the map.
    assert result == {"sess-1": 12.34, "sess-2": 5.0}
    # The requested ids are bound as the array parameter (single grouped query).
    assert conn.params == {"sids": ["sess-1", "sess-2", "sess-3"]}


def test_costs_skips_null_rows(monkeypatch: MonkeyPatch) -> None:
    conn = _FakeRowsConn([("sess-1", 1.0), (None, 9.9), ("sess-2", None)])
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "postgresql://u:p@h:5432/litellm")
    monkeypatch.setattr(ai_cost, "_spend_engine", lambda url: _FakeRowsEngine(conn))
    # Rows with a null sid or null sum are dropped, not coerced to zero.
    assert ai_cost.session_ai_costs_usd(["sess-1", "sess-2"]) == {"sess-1": 1.0}


def test_costs_none_on_read_error(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LITELLM_DATABASE_URL", "postgresql://u:p@h:5432/litellm")

    def _boom(url: str) -> _FakeRowsEngine:
        raise ConnectionError("spend table unreachable")

    monkeypatch.setattr(ai_cost, "_spend_engine", _boom)
    assert ai_cost.session_ai_costs_usd(["sess-1"]) is None
