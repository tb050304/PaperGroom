"""Tests for the deterministic half of role assignment.

The model's own accuracy can only be measured end to end against a real API
(``scripts/eval_roles.py --live``). What runs here is the part that must be
right regardless: the patterns, and — more importantly — the boundary of what
they are allowed to claim.

Claiming too little costs a model call. Claiming too much is worse: a pattern
that grabs a paragraph the model should have judged produces a confidently
wrong style, with no way for anyone to notice.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from papergroom.ai import labeler
from papergroom.ai.labeler import label_document
from papergroom.config import LLMConfig, ProcessingConfig
from papergroom.models import Document, Paragraph, Role
from papergroom.structure.patterns import certain_role, classify

FIXTURES = Path(__file__).parent / "fixtures" / "role_cases.yaml"


def _cases() -> list[dict]:
    return yaml.safe_load(FIXTURES.read_text(encoding="utf-8"))["cases"]


def _case_id(case: dict) -> str:
    return case["text"][:26]


@pytest.mark.parametrize("case", _cases(), ids=_case_id)
def test_pattern_layer_claims_exactly_what_it_should(case: dict):
    got = certain_role(case["text"])
    if case.get("pattern"):
        assert got is not None, "expected a pattern to settle this without the model"
        assert got == Role(case["role"])
    else:
        assert got is None, f"a pattern claimed {got} — the model should decide this"


def test_pattern_only_document_never_calls_the_model(monkeypatch):
    """If every paragraph is pattern-decided, the API is not touched."""
    pattern_cases = [c for c in _cases() if c.get("pattern")]
    doc = Document(
        source_path="x.docx",
        paragraphs=[
            Paragraph(index=i, text=c["text"]) for i, c in enumerate(pattern_cases)
        ],
    )
    monkeypatch.setattr(
        labeler, "LLMClient", lambda cfg, cache: pytest.fail("should not be called")
    )

    label_document(
        doc, LLMConfig("openai", "k", "http://x", "m"), None, ProcessingConfig(cache_dir=None)
    )

    assert [p.role for p in doc.paragraphs] == [Role(c["role"]) for c in pattern_cases]


def test_toc_entry_hints_unknown_not_a_heading():
    """A contents entry is shaped like a heading; the leader dots say no."""
    entry = "第2章 系统设计 ………………………………………………… 12"
    assert classify(entry) == Role.UNKNOWN
    assert certain_role(entry) is None


def test_a_numbered_heading_is_a_hint_not_a_verdict():
    """Distinguishing a heading from a list item needs the document, so the
    pattern must not claim it."""
    assert classify("1 研究背景") == Role.TITLE_L1
    assert certain_role("1 研究背景") is None
