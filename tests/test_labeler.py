"""Tests for the AI labeler with a MOCKED LLM client.

We monkeypatch :class:`papergroom.ai.labeler.LLMClient` so no network is
needed. Tests cover: batching, context overlap, JSON parsing (incl. dirty
output), low-confidence fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from papergroom.ai import labeler
from papergroom.ai.labeler import label_document
from papergroom.config import LLMConfig, ProcessingConfig
from papergroom.models import Document, Paragraph, Role


class _MockClient:
    """Records calls and returns canned JSON for each batch."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[str] = []

    def complete(self, messages, **kwargs):
        self.calls.append(messages[-1]["content"])
        if self._responses:
            return self._responses.pop(0)
        return '{"labels": []}'


def _make_llm_config() -> LLMConfig:
    return LLMConfig(
        provider="openai", api_key="sk-test", base_url="http://x/v1", model="m"
    )


def _paragraphs_from_texts(*texts: str) -> list[Paragraph]:
    return [Paragraph(index=i, text=t) for i, t in enumerate(texts)]


def test_label_document_assigns_roles(monkeypatch):
    paras = _paragraphs_from_texts(
        "Chapter 1 Introduction",
        "This is body text.",
        "Figure 1: caption here.",
    )
    doc = Document(source_path="x.docx", paragraphs=paras)

    canned = json.dumps(
        {
            "labels": [
                {"index": 0, "role": "title_l1", "confidence": 0.9},
                {"index": 1, "role": "body", "confidence": 0.95},
                {"index": 2, "role": "figure_caption", "confidence": 0.85},
            ]
        }
    )
    mock = _MockClient([canned])
    monkeypatch.setattr(labeler, "LLMClient", lambda cfg: mock)

    annotation = label_document(doc, _make_llm_config(), rules_text="test rules")

    assert doc.paragraphs[0].role == Role.TITLE_L1
    assert doc.paragraphs[1].role == Role.BODY
    assert doc.paragraphs[2].role == Role.FIGURE_CAPTION
    assert len(annotation.entries) == 3


def test_low_confidence_leaves_unknown(monkeypatch):
    paras = _paragraphs_from_texts("ambiguous text")
    doc = Document(source_path="x.docx", paragraphs=paras)
    canned = json.dumps(
        {"labels": [{"index": 0, "role": "body", "confidence": 0.3}]}
    )
    mock = _MockClient([canned])
    monkeypatch.setattr(labeler, "LLMClient", lambda cfg: mock)

    processing = ProcessingConfig(min_confidence=0.6)
    label_document(doc, _make_llm_config(), "test rules", processing)

    assert doc.paragraphs[0].role == Role.UNKNOWN
    assert doc.paragraphs[0].confidence == 0.3


def test_dirty_json_with_markdown_fences(monkeypatch):
    """Model wraps JSON in ```json ... ```; parser must still recover."""
    paras = _paragraphs_from_texts("body text")
    doc = Document(source_path="x.docx", paragraphs=paras)
    dirty = '```json\n{"labels": [{"index": 0, "role": "body", "confidence": 0.9}]}\n```'
    mock = _MockClient([dirty])
    monkeypatch.setattr(labeler, "LLMClient", lambda cfg: mock)

    label_document(doc, _make_llm_config(), "test rules")

    assert doc.paragraphs[0].role == Role.BODY


def test_unknown_role_from_model_is_ignored(monkeypatch):
    """Model emits a role outside the label set → entry dropped, not crash."""
    paras = _paragraphs_from_texts("text")
    doc = Document(source_path="x.docx", paragraphs=paras)
    canned = json.dumps(
        {"labels": [{"index": 0, "role": "made_up_role", "confidence": 0.9}]}
    )
    mock = _MockClient([canned])
    monkeypatch.setattr(labeler, "LLMClient", lambda cfg: mock)

    label_document(doc, _make_llm_config(), "test rules")
    # Falls back to UNKNOWN since the role was rejected.
    assert doc.paragraphs[0].role == Role.UNKNOWN


def test_batching_splits_large_documents(monkeypatch):
    """A document bigger than one batch triggers ≥2 LLM calls."""
    # Each paragraph ~50 chars → at 6000 tokens (24000 chars) we need ~480
    # paragraphs to force a split. Use a tiny max_tokens to force a split
    # with few paragraphs instead.
    paras = _paragraphs_from_texts(*[f"para {i} " + "x" * 40 for i in range(10)])
    doc = Document(source_path="x.docx", paragraphs=paras)

    mock = _MockClient([json.dumps({"labels": []})] * 10)
    monkeypatch.setattr(labeler, "LLMClient", lambda cfg: mock)

    processing = ProcessingConfig(max_tokens_per_batch=5)  # tiny → many batches
    label_document(doc, _make_llm_config(), "test rules", processing)

    assert len(mock.calls) >= 2, "expected multiple batches for a long doc"


def test_context_only_paragraphs_skipped(monkeypatch):
    """Carry-over context paragraphs must not be re-labeled."""
    paras = _paragraphs_from_texts("a", "b", "c", "d", "e")
    doc = Document(source_path="x.docx", paragraphs=paras)
    # Force small batches to guarantee overlap exists.
    processing = ProcessingConfig(max_tokens_per_batch=2)

    # Return role=body for whatever indices come in.
    def fake_complete(messages, **kwargs):
        # Inspect the user message to count labeled vs context lines.
        text = messages[-1]["content"]
        # labeled lines start with a bare number; context lines start with
        # context_only:true
        labeled_count = sum(
            1 for line in text.splitlines() if line and not line.startswith("context_only")
        )
        return json.dumps(
            {
                "labels": [
                    {"index": i, "role": "body", "confidence": 0.9}
                    for i in range(labeled_count)
                ]
            }
        )

    mock = _MockClient([])
    mock.complete = fake_complete  # type: ignore[assignment]
    monkeypatch.setattr(labeler, "LLMClient", lambda cfg: mock)

    label_document(doc, _make_llm_config(), "test rules", processing)
    # All 5 paragraphs end up labeled body (just via different batches).
    assert all(p.role == Role.BODY for p in doc.paragraphs)


def test_empty_document_returns_empty_annotation(monkeypatch):
    doc = Document(source_path="x.docx", paragraphs=[])
    # LLMClient should never be instantiated.
    monkeypatch.setattr(
        labeler, "LLMClient", lambda cfg: pytest.fail("should not be called")
    )
    annotation = label_document(doc, _make_llm_config(), "test rules")
    assert annotation.entries == []
