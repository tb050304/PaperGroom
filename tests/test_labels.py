"""Tests for the editable labels file (export → correct → re-import)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from papergroom.labels import LabelsError, export_labels, load_labels
from papergroom.models import Document, Paragraph, Role


def _doc() -> Document:
    return Document(
        source_path="x.docx",
        paragraphs=[
            Paragraph(index=0, text="1 研究背景", role=Role.TITLE_L1),
            Paragraph(index=1, text="正文。", role=Role.BODY),
        ],
    )


def _write(tmp_path: Path, paragraphs: list[dict]) -> Path:
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps({"paragraphs": paragraphs}, ensure_ascii=False), encoding="utf-8"
    )
    return path


def test_round_trip(tmp_path: Path):
    path = export_labels(_doc(), tmp_path / "labels.json")
    assert load_labels(path, _doc()) == {0: Role.TITLE_L1, 1: Role.BODY}


def test_an_edited_role_is_picked_up(tmp_path: Path):
    path = export_labels(_doc(), tmp_path / "labels.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["paragraphs"][1]["role"] = "quote"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert load_labels(path, _doc()) == {0: Role.TITLE_L1, 1: Role.QUOTE}


def test_unknown_role_is_rejected(tmp_path: Path):
    path = _write(tmp_path, [{"index": 0, "role": "made_up", "text": "1 研究背景"}])
    with pytest.raises(LabelsError, match="unknown role"):
        load_labels(path, _doc())


def test_out_of_range_index_is_rejected(tmp_path: Path):
    path = _write(tmp_path, [{"index": 9, "role": "body", "text": "x"}])
    with pytest.raises(LabelsError, match="does not exist"):
        load_labels(path, _doc())


def test_stale_text_is_rejected(tmp_path: Path):
    """Applying a file from another document would mislabel paragraphs."""
    path = _write(tmp_path, [{"index": 0, "role": "body", "text": "a different document"}])
    with pytest.raises(LabelsError, match="does not match"):
        load_labels(path, _doc())


def test_text_is_optional(tmp_path: Path):
    path = _write(tmp_path, [{"index": 0, "role": "body"}])
    assert load_labels(path, _doc()) == {0: Role.BODY}


def test_empty_paragraphs_are_not_exported(tmp_path: Path):
    doc = Document(
        source_path="x",
        paragraphs=[
            Paragraph(index=0, text="", is_empty=True),
            Paragraph(index=1, text="正文。", role=Role.BODY),
        ],
    )

    data = json.loads(export_labels(doc, tmp_path / "l.json").read_text(encoding="utf-8"))

    assert [p["index"] for p in data["paragraphs"]] == [1]
