"""Tests for the CLI pipeline, with the model mocked out.

These run the real parse → structure → ruleset → write path; only the LLM is
stubbed, so they cover the plumbing that unit tests of the layers miss.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument

from papergroom import cli


def _docx(path: Path) -> Path:
    document = DocxDocument()
    document.add_paragraph("1 研究背景 当前高校课程论文格式规范问题很多。")
    document.add_paragraph("正文段落，描述研究方法与实验结果。")
    document.save(str(path))
    return path


def _stub_model(monkeypatch) -> None:
    monkeypatch.setattr(cli, "get_llm_config", lambda: object())
    monkeypatch.setattr(cli, "label_document", lambda *args, **kwargs: None)


def _run(src: Path, out: Path, **overrides):
    options = dict(
        rules=None,
        word_styles=False,
        labels=None,
        export_labels_path=None,
        report=False,
        debug_annotation=False,
        dry_run=False,
        verbose=False,
    )
    options.update(overrides)
    return cli._process_one(src, out, **options)


def test_a_normal_run_writes_the_document(tmp_path: Path, monkeypatch):
    src = _docx(tmp_path / "in.docx")
    out = tmp_path / "out.docx"
    _stub_model(monkeypatch)

    _run(src, out)

    assert out.exists()
    written = DocxDocument(str(out))
    assert len(written.paragraphs) == 3  # the merged paragraph was split


def test_dry_run_does_not_write_the_document(tmp_path: Path, monkeypatch):
    src = _docx(tmp_path / "in.docx")
    out = tmp_path / "out.docx"
    _stub_model(monkeypatch)

    result = _run(src, out, dry_run=True)

    assert result == out.resolve()
    assert not out.exists()


def test_dry_run_can_still_write_a_report(tmp_path: Path, monkeypatch):
    """The report is how you inspect a dry run, so it must still be written."""
    src = _docx(tmp_path / "in.docx")
    out = tmp_path / "out.docx"
    _stub_model(monkeypatch)

    _run(src, out, dry_run=True, report=True)

    assert not out.exists()
    assert (tmp_path / "out.report.html").exists()


def test_a_corrupt_document_is_reported_as_a_processing_error(
    tmp_path: Path, monkeypatch
):
    import pytest

    src = tmp_path / "broken.docx"
    src.write_text("not a docx", encoding="utf-8")
    _stub_model(monkeypatch)

    with pytest.raises(cli.ProcessingError, match="cannot read"):
        _run(src, tmp_path / "out.docx")
