"""Tests for LLM client network configuration. No network access needed.

The behaviour under test is the proxy policy. On Windows, httpx's default
``trust_env=True`` also reads the system proxy from the registry. When that
proxy is configured for something unrelated, it silently captures API
requests and the failure surfaces as a bare "Connection error" — which is
exactly what happened during development, and cost a debugging session to
identify.
"""

from __future__ import annotations

import pytest

from papergroom.ai import client


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch):
    for var in ("LLM_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "LLM_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)


def test_direct_connection_by_default():
    assert client.resolve_proxy() is None


def test_llm_proxy_wins_over_conventional_names(monkeypatch):
    monkeypatch.setenv("LLM_PROXY", "http://explicit:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://conventional:2")
    assert client.resolve_proxy() == "http://explicit:1"


def test_conventional_proxy_is_honoured(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://conventional:2")
    assert client.resolve_proxy() == "http://conventional:2"


def test_http_proxy_is_the_last_fallback(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://plain:3")
    assert client.resolve_proxy() == "http://plain:3"


def test_client_does_not_trust_the_environment():
    """An OS-wide proxy must not be adopted implicitly."""
    http = client.build_http_client()
    try:
        assert http.trust_env is False
    finally:
        http.close()


def test_an_explicit_proxy_is_passed_to_the_client(monkeypatch):
    seen: dict = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(client.httpx2, "Client", _FakeClient)
    monkeypatch.setenv("LLM_PROXY", "http://explicit:1")

    client.build_http_client()

    assert seen["proxy"] == "http://explicit:1"
    assert seen["trust_env"] is False


def test_default_timeout():
    assert client._timeout() == 120.0


def test_bad_timeout_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "not-a-number")
    assert client._timeout() == 120.0
