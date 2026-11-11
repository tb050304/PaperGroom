"""Tests for the HTML review report."""

from __future__ import annotations

from pathlib import Path

from papergroom.models import Document, Paragraph, ParagraphStyle, Role
from papergroom.report import render_html, write_report
from papergroom.rules.schema import Ruleset


def _doc() -> Document:
    return Document(
        source_path="input.docx",
        paragraphs=[
            Paragraph(
                index=0,
                text="1 研究背景",
                role=Role.TITLE_L1,
                confidence=0.9,
                resolved_style=ParagraphStyle(
                    font_name_east_asian="黑体", font_size_pt=16, bold=True, alignment="left"
                ),
            ),
            Paragraph(
                index=1,
                text="正文内容",
                role=Role.BODY,
                confidence=0.95,
                resolved_style=ParagraphStyle(
                    font_name_east_asian="宋体",
                    font_size_pt=12,
                    alignment="justify",
                    first_line_indent_chars=2,
                ),
            ),
            Paragraph(
                index=2,
                text="某个不确定的段落",
                role=Role.UNKNOWN,
                confidence=0.0,
                resolved_style=ParagraphStyle(),
            ),
            Paragraph(
                index=3,
                text="<script>alert(1)</script>",
                role=Role.BODY,
                confidence=0.3,
                resolved_style=ParagraphStyle(font_size_pt=12),
            ),
        ],
    )


def test_report_shows_roles_and_applied_styles():
    page = render_html(_doc(), Ruleset(name="standard_thesis"), output_name="out.docx")

    assert "1 研究背景" in page
    assert "title_l1" in page
    assert "黑体" in page
    assert "两端对齐" in page
    assert "standard_thesis" in page


def test_uncertain_paragraphs_are_marked():
    page = render_html(_doc(), None)

    # UNKNOWN and below-threshold rows are both highlighted.
    assert page.count("uncertain") >= 2
    assert '<tr class="g-unknown uncertain">' in page


def test_text_is_html_escaped():
    page = render_html(_doc(), None)

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_summary_counts():
    page = render_html(_doc(), None, min_confidence=0.6)

    assert "<b>4</b>段落" in page
    assert "<b>3</b>已确定角色" in page
    assert "<b>1</b>未确定" in page
    assert "<b>2</b>需要人工确认" in page


def test_write_report_creates_a_standalone_file(tmp_path: Path):
    out = write_report(_doc(), None, tmp_path / "report.html")

    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "<style>" in text  # inline CSS: no external assets
