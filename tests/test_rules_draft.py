"""Tests for the natural-language ruleset drafter. The model is mocked."""

from __future__ import annotations

import pytest

from papergroom.ai import rules_draft
from papergroom.ai.rules_draft import build_messages, draft_rules, strip_fences, validate_draft
from papergroom.config import LLMConfig
from papergroom.rules.loader import load_ruleset


def _config() -> LLMConfig:
    return LLMConfig("openai", "k", "http://x", "m")


def _mock(monkeypatch, reply: str) -> None:
    class Mock:
        def __init__(self, config):
            pass

        def complete(self, messages, **kwargs):
            return reply

    monkeypatch.setattr(rules_draft, "LLMClient", Mock)


def test_strip_fences_removes_a_yaml_fence():
    assert strip_fences("```yaml\nname: x\n```") == "name: x\n"


def test_strip_fences_leaves_plain_yaml():
    assert strip_fences("name: x\n") == "name: x\n"


def test_draft_is_stripped_and_validates(monkeypatch):
    _mock(
        monkeypatch,
        "```yaml\nname: school\nextends: standard_thesis\nstyles:\n"
        "  body:\n    font_size_pt: 14\n```",
    )

    text = draft_rules("正文用四号", _config())

    assert "```" not in text
    ruleset = validate_draft(text)
    assert ruleset.extends == "standard_thesis"
    assert ruleset.styles["body"].font_size_pt == 14


def test_validate_rejects_a_misspelled_field():
    with pytest.raises(ValueError, match="validation"):
        validate_draft("name: x\nstyles:\n  body:\n    font_size: 12\n")


def test_validate_rejects_a_non_mapping():
    with pytest.raises(ValueError, match="mapping"):
        validate_draft("- just\n- a list\n")


def test_prompt_carries_roles_base_and_units():
    messages = build_messages(
        "正文用四号", load_ruleset("standard_thesis"), "standard_thesis"
    )
    system = messages[0]["content"]

    assert "extends: standard_thesis" in system
    assert "title_l1" in system
    assert "小四 = 12" in system
    assert "table_borders" in system
