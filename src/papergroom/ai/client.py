"""Thin OpenAI-compatible LLM client.

One class, one method. The same client works against Volcengine Ark,
OpenAI proper, and local servers (Ollama / vLLM) because they all speak
the OpenAI Chat Completions protocol.

We intentionally do NOT add retries, streaming, or rate limiting here.
Stage 1 keeps the moving parts minimal; those concerns land in Stage 3
(accuracy) / Stage 4 (batch) where they are justified by real failures.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from ..config import LLMConfig
from .cache import ResponseCache


class LLMClient:
    """OpenAI-compatible chat client.

    Built from :class:`LLMConfig`. The ``complete`` method returns parsed
    JSON when ``response_format`` is requested, otherwise raw text.

    An optional :class:`ResponseCache` short-circuits identical requests,
    which matters when iterating on the prompt or the rules.
    """

    def __init__(self, config: LLMConfig, cache: ResponseCache | None = None):
        self._config = config
        self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        self._model = config.model
        self._cache = cache

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: dict[str, str] | None = {"type": "json_object"},
        max_tokens: int | None = None,
    ) -> str:
        """Call chat.completions.create and return the assistant content.

        Args:
            messages: OpenAI-style message list.
            temperature: 0.0 for deterministic labeling.
            response_format: Pass None to disable JSON mode, or
                ``{"type": "json_object"}`` to force JSON output.
            max_tokens: Optional cap on completion length.

        Returns:
            The assistant's text content (string). Caller parses JSON if
            ``response_format`` was set.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        if self._cache is not None:
            cached = self._cache.get(kwargs)
            if cached is not None:
                return cached

        resp = self._client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""

        if self._cache is not None:
            self._cache.put(kwargs, content)
        return content
