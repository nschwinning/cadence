"""Tests for the push-notification abstraction (Pushover + null, no network).

Pushover HTTP is exercised by monkeypatching ``requests.post`` so no request ever
leaves the process; credentials are set via the ``settings`` singleton.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from cadence.config import settings
from cadence.notify import NullNotifier, PushoverNotifier, get_notifier
from cadence.notify.pushover import _PUSHOVER_URL


class _FakeResponse:
    def __init__(self, *, ok: bool = True, status_code: int = 200, text: str = "") -> None:
        self.ok = ok
        self.status_code = status_code
        self.text = text


@pytest.fixture
def pushover_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PUSHOVER_USER", "user-key", raising=False)
    monkeypatch.setattr(settings, "PUSHOVER_TOKEN", "app-token", raising=False)


def test_pushover_send_posts_expected_payload(
    monkeypatch: pytest.MonkeyPatch, pushover_creds: None
) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse(ok=True)

    monkeypatch.setattr(requests, "post", fake_post)

    result = PushoverNotifier().send("hello", title="Cadence")

    assert result is True
    assert captured["url"] == _PUSHOVER_URL
    payload = captured["kwargs"]["data"]
    assert payload["user"] == "user-key"
    assert payload["token"] == "app-token"
    assert payload["message"] == "hello"
    assert payload["title"] == "Cadence"
    assert captured["kwargs"]["timeout"] > 0


def test_pushover_send_omits_title_when_absent(
    monkeypatch: pytest.MonkeyPatch, pushover_creds: None
) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["kwargs"] = kwargs
        return _FakeResponse(ok=True)

    monkeypatch.setattr(requests, "post", fake_post)

    assert PushoverNotifier().send("body only") is True
    assert "title" not in captured["kwargs"]["data"]


def test_pushover_send_without_credentials_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PUSHOVER_USER", "", raising=False)
    monkeypatch.setattr(settings, "PUSHOVER_TOKEN", "", raising=False)
    called = False

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        nonlocal called
        called = True
        return _FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    assert PushoverNotifier().send("hi") is False
    assert called is False  # never touched the network


def test_pushover_send_returns_false_on_transport_error(
    monkeypatch: pytest.MonkeyPatch, pushover_creds: None
) -> None:
    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(requests, "post", fake_post)

    # Never raises, reports failure.
    assert PushoverNotifier().send("hi") is False


def test_pushover_send_returns_false_on_non_2xx(
    monkeypatch: pytest.MonkeyPatch, pushover_creds: None
) -> None:
    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(ok=False, status_code=429, text="rate limited")

    monkeypatch.setattr(requests, "post", fake_post)

    assert PushoverNotifier().send("hi") is False


def test_null_notifier_is_noop() -> None:
    assert NullNotifier().send("hi", title="t") is False


def test_get_notifier_selects_by_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PUSHOVER_USER", "u", raising=False)
    monkeypatch.setattr(settings, "PUSHOVER_TOKEN", "t", raising=False)
    assert isinstance(get_notifier(), PushoverNotifier)

    monkeypatch.setattr(settings, "PUSHOVER_TOKEN", "", raising=False)
    assert isinstance(get_notifier(), NullNotifier)
