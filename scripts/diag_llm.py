"""Check that the configured LLM endpoint is reachable and answers.

Run after editing ``.env``:

    python scripts/diag_llm.py

It prints the resolved provider, endpoint, model and proxy, then makes one
small call. If that fails, the error is the provider's own message rather
than a bare "Connection error", which is what makes it useful.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papergroom.ai.client import LLMClient, resolve_proxy  # noqa: E402
from papergroom.config import get_llm_config  # noqa: E402


def main() -> int:
    try:
        config = get_llm_config()
    except Exception as e:
        print(f"CONFIG ERROR: {type(e).__name__}: {e}")
        print("\nEdit .env in the project root. See .env.example for the shapes.")
        return 1

    print(f"provider : {config.provider}")
    print(f"base_url : {config.base_url}")
    print(f"model    : {config.model}")
    print(f"api_key  : (set, {len(config.api_key)} chars)")
    print(f"proxy    : {resolve_proxy() or '(direct connection)'}")
    print("-" * 60)

    try:
        client = LLMClient(config)
        reply = client.complete(
            [{"role": "user", "content": "Reply with exactly: ok"}],
            response_format=None,
        )
        print(f"OK: {reply.strip()[:100]!r}")
        return 0
    except Exception as e:
        print(f"FAILED: {type(e).__name__}")
        print(str(e)[:800])
        print("\nIf the message mentions a subscription or model access, the")
        print("endpoint is reachable and the problem is the account/provider.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
