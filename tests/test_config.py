"""Tests for provider selection. No network access needed."""

from __future__ import annotations

import pytest

from papergroom import config as config_module
from papergroom.config import get_llm_config

_PROVIDER_VARS = (
    "LLM_PROVIDER",
    "ARK_API_KEY",
    "ARK_BASE_URL",
    "ARK_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "LOCAL_API_KEY",
    "LOCAL_BASE_URL",
    "LOCAL_MODEL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
)


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    # Never let the developer's real .env leak into these assertions.
    monkeypatch.setattr(config_module, "_load_env", lambda: None)
    for name in _PROVIDER_VARS:
        monkeypatch.delenv(name, raising=False)


def test_custom_provider_reads_neutral_names(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_API_KEY", "sk-new")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")

    config = get_llm_config()

    assert config.provider == "custom"
    assert config.api_key == "sk-new"
    assert config.base_url == "https://api.deepseek.com/v1"
    assert config.model == "deepseek-chat"


def test_custom_requires_a_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_API_KEY", "sk-new")
    monkeypatch.setenv("LLM_MODEL", "m")

    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        get_llm_config()


def test_unknown_provider_lists_the_choices(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")

    with pytest.raises(ValueError, match=r"ark \| openai \| local \| custom"):
        get_llm_config()


def test_missing_api_key_is_reported(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    with pytest.raises(ValueError, match="No API key"):
        get_llm_config()


def test_local_needs_no_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_MODEL", "qwen2.5:7b")

    assert get_llm_config().api_key == "local"
