"""Tests for structure recovery.

The fixture-driven test at the top is the real specification: the cases in
``tests/fixtures/segment_cases.yaml`` describe which splits are wanted and —
more importantly — which are not. The tests below it pin invariants that
must hold for every input, including inputs nobody thought to write a
fixture for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from papergroom.models import Document, Paragraph
from papergroom.structure import segment_text, structurize

FIXTURES = Path(__file__).parent / "fixtures" / "segment_cases.yaml"


def _load_cases() -> list[dict]:
    return yaml.safe_load(FIXTURES.read_text(encoding="utf-8"))["cases"]


def _case_id(case: dict) -> str:
    return case["text"][:28]


@pytest.mark.parametrize("case", _load_cases(), ids=_case_id)
def test_fixture_case(case: dict):
    """Segment texts and role hints match the fixture exactly."""
    got = segment_text(case["text"])
    assert [s.text for s in got] == [e["text"] for e in case["expect"]]
    assert [s.role_hint.value if s.role_hint else None for s in got] == [
        e.get("role") for e in case["expect"]
    ]


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _load_cases(), ids=_case_id)
def test_offsets_match_text(case: dict):
    """Each segment's offsets really select its text from the source."""
    text = case["text"]
    for seg in segment_text(text):
        assert text[seg.start : seg.end] == seg.text
        assert 0 <= seg.start < seg.end <= len(text)


@pytest.mark.parametrize("case", _load_cases(), ids=_case_id)
def test_segments_are_ordered_and_disjoint(case: dict):
    segments = segment_text(case["text"])
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.end <= later.start


@pytest.mark.parametrize("case", _load_cases(), ids=_case_id)
def test_segmentation_is_a_fixed_point(case: dict):
    """Re-segmenting a segment yields one segment.

    Structure recovery runs once, but a rule that keeps re-firing on its own
    output would be a latent infinite loop — this catches that.
    """
    for seg in segment_text(case["text"]):
        again = segment_text(seg.text)
        assert len(again) == 1, f"{seg.text!r} re-split into {[s.text for s in again]}"


def test_empty_and_whitespace_input():
    assert [s.text for s in segment_text("")] == [""]
    assert [s.text for s in segment_text("   ")] == ["   "]


# ---------------------------------------------------------------------------
# structurize(): the document-level pass
# ---------------------------------------------------------------------------


def test_structurize_splits_and_records_plan():
    doc = Document(
        source_path="x.docx",
        paragraphs=[
            Paragraph(index=0, text="基于AI在前端中的研究", source_index=0),
            Paragraph(index=1, text="1 研究背景 当前高校课程论文格式规范问题很多。", source_index=1),
        ],
    )

    structurize(doc)

    assert [p.text for p in doc.paragraphs] == [
        "基于AI在前端中的研究",
        "1 研究背景",
        "当前高校课程论文格式规范问题很多。",
    ]
    # Indices are renumbered consecutively; source_index records provenance.
    assert [p.index for p in doc.paragraphs] == [0, 1, 2]
    assert [p.source_index for p in doc.paragraphs] == [0, 1, 1]
    # Only the split paragraph appears in the plan, with its char ranges.
    assert doc.splits == {1: [(0, 6), (7, len("1 研究背景 当前高校课程论文格式规范问题很多。"))]}


def test_structurize_leaves_unmerged_documents_alone():
    texts = ["摘要", "本文研究排版问题。", "[1] 张三. 甲[J]. 学报, 2020."]
    doc = Document(
        source_path="x.docx",
        paragraphs=[Paragraph(index=i, text=t, source_index=i) for i, t in enumerate(texts)],
    )

    structurize(doc)

    assert [p.text for p in doc.paragraphs] == texts
    assert doc.splits == {}


def test_structurize_never_splits_paragraphs_with_objects():
    """A hyperlink makes character offsets ambiguous — skip, don't guess."""
    doc = Document(
        source_path="x.docx",
        paragraphs=[
            Paragraph(
                index=0,
                text="1 研究背景 当前高校课程论文格式规范问题很多。",
                has_hyperlink=True,
                source_index=0,
            )
        ],
    )

    structurize(doc)

    assert len(doc.paragraphs) == 1
    assert doc.splits == {}
