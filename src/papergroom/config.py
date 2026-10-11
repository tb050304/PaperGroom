"""Runtime configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class LLMConfig:
    """Resolved LLM configuration for the OpenAI-compatible client."""

    provider: str
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class ProcessingConfig:
    """Tunable processing parameters."""

    max_concurrency: int = 4
    max_tokens_per_batch: int = 6000
    min_confidence: float = 0.6
    debug_annotation: bool = False


def _load_env() -> None:
    """Load .env from CWD if present. Never raises if missing."""
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        load_dotenv(cwd_env, override=False)


def get_llm_config() -> LLMConfig:
    """Build an LLMConfig from environment variables.

    Provider is selected via ``LLM_PROVIDER`` (ark | openai | local). For each
    provider a matching ``(api_key, base_url, model)`` triple is read.
    """
    _load_env()
    provider = (os.getenv("LLM_PROVIDER") or "ark").strip().lower()

    if provider == "ark":
        api_key = os.getenv("ARK_API_KEY", "")
        base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        model = os.getenv("ARK_MODEL", "")
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    elif provider == "local":
        api_key = os.getenv("LOCAL_API_KEY", "local")
        base_url = os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1")
        model = os.getenv("LOCAL_MODEL", "qwen2.5:7b")
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")

    if not api_key:
        raise ValueError(
            f"No API key configured for provider {provider!r}. "
            f"Copy .env.example to .env and fill in your key."
        )
    if not model:
        raise ValueError(
            f"No model configured for provider {provider!r}. "
            f"Set the matching *_MODEL env var in .env."
        )

    return LLMConfig(provider=provider, api_key=api_key, base_url=base_url, model=model)


def get_processing_config(debug_annotation: bool | None = None) -> ProcessingConfig:
    """Build ProcessingConfig from environment, with optional CLI overrides."""
    _load_env()
    return ProcessingConfig(
        max_concurrency=_int_env("MAX_CONCURRENCY", 4),
        max_tokens_per_batch=_int_env("MAX_TOKENS_PER_BATCH", 6000),
        min_confidence=_float_env("MIN_CONFIDENCE", 0.6),
        debug_annotation=debug_annotation
        if debug_annotation is not None
        else _bool_env("DEBUG_ANNOTATION", False),
    )


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
