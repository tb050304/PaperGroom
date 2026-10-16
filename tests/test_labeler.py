"""Tests for the role labeler and the style resolver.

Everything here runs against a MOCKED LLM client — no network, no API key.
The split under test is the core of the rework: patterns decide what they
can and are never sent to a model; the model decides the rest; the ruleset
decides styles, and the model never sees a style at all.
"""

from __future__ import annotations

import json

import pytest

from papergroom.ai import labeler
from papergroom.ai.labeler import label_document
from papergroom.config import LLMConfig, ProcessingConfig
from papergroom.models import Document, Paragraph, Role
from papergroom.rules.resolve import resolve_styles
from papergroom.rules.schema import ParagraphStyle, Ruleset


class _MockClient:
    """Records the user message of each call; returns canned JSON in order."""

    def __init__(self, responses: list[str] | None = None):
        self._responses = list(responses or [])
        self.calls: list[str] = []

    def complete(self, messages, **kwargs):
        self.calls.append(messages[-1]["content"])
        return self._responses.pop(0) if self._responses else '{"labels": []}'


def _processing(**kwargs) -> ProcessingConfig:
    # cache_dir=None keeps tests off the disk.
    kwargs.setdefault("cache_dir", None)
    return ProcessingConfig(**kwargs)


def _llm_config() -> LLMConfig:
    return LLMConfig(provider="openai", api_key="sk-test", base_url="http://x/v1", model="m")


def _doc(*texts: str) -> Document:
    return Document(
        source_path="x.docx",
        paragraphs=[Paragraph(index=i, text=t) for i, t in enumerate(texts)],
    )


def _install(monkeypatch, mock: _MockClient) -> None:
    monkeypatch.setattr(labeler, "LLMClient", lambda cfg, cache: mock)


def _labels(*entries: tuple[int, str, float]) -> str:
    return json.dumps(
        {
            "labels": [
                {"index": i, "role": role, "confidence": conf}
                for i, role, conf in entries
            ]
        }
    )


def _answerable_lines(text: str) -> list[str]:
    """Lines the model is expected to label (no context/fixed marker)."""
    return [
        line
        for line in text.splitlines()
        if line and not line.startswith(("context_only", "fixed"))
    ]


# ---------------------------------------------------------------------------
# Patterns vs the model
# ---------------------------------------------------------------------------


def test_pattern_decided_paragraph_is_never_sent_for_labeling(monkeypatch):
    """A bibliography heading is settled by pattern, not by a model call."""
    doc = _doc("参考文献：", "本文研究排版问题并提出了一种自动化方案。")
    mock = _MockClient([_labels((1, "body", 0.9))])
    _install(monkeypatch, mock)

    label_document(doc, _llm_config(), None, _processing())

    assert doc.paragraphs[0].role == Role.TITLE_L1
    assert doc.paragraphs[0].confidence == 1.0
    assert doc.paragraphs[1].role == Role.BODY
    # The decided paragraph is shown for context, marked, and not asked about.
    assert "fixed(title_l1) 0: 参考文献" in mock.calls[0]


def test_model_cannot_overwrite_a_pattern_decision(monkeypatch):
    """A contradictory response leaves the pattern's answer standing."""
    doc = _doc("[1] 张三. 甲[J]. 学报, 2020.", "正文段落，描述研究方法与实验结果。")
    # The model answers for an index it was not offered.
    mock = _MockClient([_labels((0, "body", 0.99))])
    _install(monkeypatch, mock)

    label_document(doc, _llm_config(), None, _processing())

    assert doc.paragraphs[0].role == Role.REFERENCE


def test_hint_is_shown_to_the_model(monkeypatch):
    """Numbered headings are a hint, not a verdict — the model decides."""
    doc = _doc("1.1 传统排版存在的问题")
    mock = _MockClient([_labels((0, "title_l2", 0.9))])
    _install(monkeypatch, mock)

    label_document(doc, _llm_config(), None, _processing())

    assert "hint(title_l2)" in mock.calls[0]
    assert doc.paragraphs[0].role == Role.TITLE_L2


def test_batch_with_nothing_left_to_label_makes_no_call(monkeypatch):
    doc = _doc("参考文献：", "致谢")
    mock = _MockClient()
    _install(monkeypatch, mock)

    label_document(doc, _llm_config(), None, _processing())

    assert mock.calls == []
    assert [p.role for p in doc.paragraphs] == [Role.TITLE_L1, Role.TITLE_L1]


# ---------------------------------------------------------------------------
# Response handling
# ---------------------------------------------------------------------------


def test_low_confidence_leaves_unknown(monkeypatch):
    doc = _doc("某段无法判断的文字内容。")
    _install(monkeypatch, _MockClient([_labels((0, "body", 0.3))]))

    label_document(doc, _llm_config(), None, _processing(min_confidence=0.6))

    assert doc.paragraphs[0].role == Role.UNKNOWN
    assert doc.paragraphs[0].confidence == 0.3


def test_markdown_fences_are_tolerated(monkeypatch):
    doc = _doc("某段正文内容，描述实验。")
    dirty = "```json\n" + _labels((0, "body", 0.9)) + "\n```"
    _install(monkeypatch, _MockClient([dirty]))

    label_document(doc, _llm_config(), None, _processing())

    assert doc.paragraphs[0].role == Role.BODY


def test_unknown_role_name_is_dropped(monkeypatch):
    doc = _doc("某段正文内容，描述实验。")
    _install(monkeypatch, _MockClient([_labels((0, "made_up_role", 0.9))]))

    label_document(doc, _llm_config(), None, _processing())

    assert doc.paragraphs[0].role == Role.UNKNOWN


def test_a_failing_batch_does_not_abort_the_run(monkeypatch, capsys):
    """A network or JSON failure leaves that batch unlabeled, not crashed."""
    doc = _doc("某段正文内容，描述实验。")
    mock = _MockClient()

    def boom(messages, **kwargs):
        raise RuntimeError("connection reset")

    mock.complete = boom  # type: ignore[assignment]
    _install(monkeypatch, mock)

    label_document(doc, _llm_config(), None, _processing())

    assert doc.paragraphs[0].role == Role.UNKNOWN
    assert "labeling batch failed" in capsys.readouterr().err


def test_empty_document_makes_no_call(monkeypatch):
    doc = Document(source_path="x.docx", paragraphs=[])
    monkeypatch.setattr(
        labeler, "LLMClient", lambda cfg, cache: pytest.fail("should not be called")
    )

    assert label_document(doc, _llm_config(), None, _processing()).entries == []


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def test_large_documents_are_split_into_batches(monkeypatch):
    doc = _doc(*[f"para {i} " + "x" * 40 for i in range(10)])
    mock = _MockClient([_labels((0, "body", 0.9))] * 10)
    _install(monkeypatch, mock)

    label_document(doc, _llm_config(), None, _processing(max_tokens_per_batch=5))

    assert len(mock.calls) >= 2


def test_context_paragraphs_are_not_labeled_twice(monkeypatch):
    """Carried-over paragraphs appear as context but are never asked about."""
    doc = _doc(*[f"正文段落 {i}，描述了研究方法与实验结果。" for i in range(6)])
    mock = _MockClient()

    def answer(messages, **kwargs):
        mock.calls.append(messages[-1]["content"])
        lines = _answerable_lines(messages[-1]["content"])
        return _labels(*[(int(line.split(":")[0]), "body", 0.9) for line in lines])

    mock.complete = answer  # type: ignore[assignment]
    _install(monkeypatch, mock)

    label_document(doc, _llm_config(), None, _processing(max_tokens_per_batch=2))

    assert all(p.role == Role.BODY for p in doc.paragraphs)
    assert len(mock.calls) >= 2


def test_display_indices_never_collide(monkeypatch):
    """A fixed line and an answerable line must not share a number."""
    doc = _doc("参考文献：", "本文研究排版问题并提出了一种自动化方案。")
    mock = _MockClient([_labels((1, "body", 0.9))])
    _install(monkeypatch, mock)

    label_document(doc, _llm_config(), None, _processing())

    numbers = [line.split(":")[0].split()[-1] for line in mock.calls[0].splitlines()]
    assert len(numbers) == len(set(numbers))


# ---------------------------------------------------------------------------
# Style resolution — the half the model never touches
# ---------------------------------------------------------------------------


def test_resolve_styles_applies_the_ruleset():
    doc = _doc("1 研究背景", "本文研究排版问题。")
    doc.paragraphs[0].role = Role.TITLE_L1
    doc.paragraphs[1].role = Role.BODY
    ruleset = Ruleset(
        name="t",
        styles={
            "title_l1": ParagraphStyle(font_size_pt=16, bold=True),
            "body": ParagraphStyle(font_size_pt=12, alignment="justify"),
        },
    )

    resolve_styles(doc, ruleset)

    assert doc.paragraphs[0].resolved_style.font_size_pt == 16
    assert doc.paragraphs[1].resolved_style.font_size_pt == 12


def test_resolve_styles_leaves_unlisted_roles_alone():
    """A role the ruleset is silent about resolves to 'change nothing'."""
    doc = _doc("某个无法判断的段落。")
    doc.paragraphs[0].role = Role.UNKNOWN

    resolve_styles(
        doc, Ruleset(name="t", styles={"body": ParagraphStyle(font_size_pt=12)})
    )

    assert doc.paragraphs[0].resolved_style.is_empty()


def test_styles_come_only_from_the_ruleset(monkeypatch):
    """The model's answer picks the role, and the role picks the style — but
    the model never supplies a style value itself."""
    doc = _doc("某个段落的内容，描述实验与结论。")
    _install(monkeypatch, _MockClient([_labels((0, "body", 0.9))]))

    label_document(doc, _llm_config(), None, _processing())
    resolve_styles(doc, Ruleset(name="t", styles={"body": ParagraphStyle(font_size_pt=12)}))

    assert doc.paragraphs[0].resolved_style.font_size_pt == 12
    assert doc.paragraphs[0].resolved_style.bold is None
