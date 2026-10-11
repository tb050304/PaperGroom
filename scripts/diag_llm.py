"""One-shot diagnostic: call the configured LLM and print raw response + error.

Run: .venv\Scripts\python.exe scripts\diag_llm.py
"""

from __future__ import annotations

import json
import sys
import traceback

from dotenv import load_dotenv

load_dotenv(".env")

import os

from openai import OpenAI

api_key = os.getenv("ARK_API_KEY", "")
base_url = os.getenv("ARK_BASE_URL", "")
model = os.getenv("ARK_MODEL", "")

print(f"provider=ark  base_url={base_url}  model={model}")
print(f"api_key={api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''}")
print("-" * 60)

client = OpenAI(api_key=api_key, base_url=base_url)

messages = [
    {
        "role": "system",
        "content": "Return strict JSON: {\"role\": \"body\", \"confidence\": 0.9}",
    },
    {"role": "user", "content": "0: This is a test paragraph."},
]

# Try 1: with response_format json_object (what the labeler uses)
print("[try1] chat.completions with response_format=json_object")
try:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    print("OK:", repr(resp.choices[0].message.content))
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:500])

print("-" * 60)

# Try 2: without response_format
print("[try2] chat.completions WITHOUT response_format")
try:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    print("OK:", repr(resp.choices[0].message.content))
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:500])

print("-" * 60)

# Try 3: minimal ping
print("[try3] minimal ping")
try:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "say hi"}],
    )
    print("OK:", repr(resp.choices[0].message.content)[:200])
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:500])
