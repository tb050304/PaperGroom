"""Tests for the rule engine (schema, loader, applier).

Loader + schema: build a ruleset from YAML and from the built-in pack.
Applier: apply to a hand-built docx, then read it back to verify the
styles landed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from papergroom.models import Document, Paragraph, Role
from papergroom.rules import load_ruleset
from papergroom.rules.applier import apply_ruleset
from papergroom.rules.schema import ParagraphStyle, Ruleset


# ---------- schema / loader ----------


def test_load_builtin_ruleset():
    ruleset = load_ruleset("standard_thesis")
    assert ruleset.name == "standard_thesis"
    # Common roles must be present.
    for role in ["title_l1", "body", "figure_caption", "reference"]:
        assert role in ruleset.styles


def test_load_from_yaml_string(tmp_path: Path):
    yaml_text = """
name: test_rules
version: 1
defaults:
  font_size_pt: 12
  alignment: justify
styles:
  title_l1:
    font_size_pt: 16
    bold: true
    alignment: center
"""
    p = tmp_path / "test.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    ruleset = load_ruleset(str(p))
    assert ruleset.name == "test_rules"
    assert ruleset.styles["title_l1"].bold is True


def test_ruleset_style_does_not_merge_defaults():
    """New architecture: defaults are NOT merged into role styles.

    Only the role's explicitly-set fields are returned; everything else
    is None (= "do not change"). This prevents accidental over-formatting.
    """
    ruleset = Ruleset(
        name="t",
        defaults=ParagraphStyle(font_size_pt=12, alignment="justify"),
        styles={"title_l1": ParagraphStyle(font_size_pt=16, bold=True)},
    )
    style = ruleset.style_for("title_l1")
    assert style.font_size_pt == 16
    assert style.bold is True
    # alignment is NOT inherited from defaults.
    assert style.alignment is None


def test_schema_rejects_bad_alignment():
    with pytest.raises(Exception):
        ParagraphStyle(alignment="diagonal")


def test_schema_rejects_bad_color():
    with pytest.raises(Exception):
        ParagraphStyle(color_hex="not-a-color")


# ---------- applier ----------


def _build_docx_with_body(tmp_path: Path) -> tuple[Path, DocxDocument]:
    """Build a small docx with 2 paragraphs; return (path, doc)."""
    doc = DocxDocument()
    doc.add_paragraph("First body paragraph.")
    doc.add_paragraph("Second body paragraph.")
    path = tmp_path / "apply_test.docx"
    doc.save(str(path))
    # Reopen so the python-docx object is detached from the builder.
    return path, DocxDocument(str(path))


def test_apply_sets_body_first_line_indent(tmp_path: Path):
    path, docx_doc = _build_docx_with_body(tmp_path)

    # Model: 2 paragraphs both labeled body, with AI-resolved styles.
    body_style = ParagraphStyle(
        font_size_pt=12,
        alignment="justify",
        first_line_indent_chars=2,
    )
    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(
                index=0, text="First body paragraph.",
                role=Role.BODY, resolved_style=body_style,
            ),
            Paragraph(
                index=1, text="Second body paragraph.",
                role=Role.BODY, resolved_style=body_style,
            ),
        ],
    )

    apply_ruleset(model, None, docx_doc)

    p0 = docx_doc.paragraphs[0]
    assert p0.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    # 2 chars * 12pt = 24pt first-line indent.
    assert p0.paragraph_format.first_line_indent == Pt(24)
    # Run font size should be set.
    assert p0.runs[0].font.size == Pt(12)


def test_apply_unknown_role_with_empty_style_leaves_paragraph(tmp_path: Path):
    """Unknown role + no resolved_style → paragraph untouched."""
    path, docx_doc = _build_docx_with_body(tmp_path)
    # Give the paragraph a distinctive alignment so we can check it survives.
    docx_doc.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    model = Document(
        source_path=str(path),
        paragraphs=[Paragraph(index=0, text="x", role=Role.UNKNOWN)],
    )

    apply_ruleset(model, None, docx_doc)

    # Alignment should be preserved (RIGHT was set above).
    assert docx_doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.RIGHT


def test_apply_east_asian_font_landed_on_run(tmp_path: Path):
    path, docx_doc = _build_docx_with_body(tmp_path)
    body_style = ParagraphStyle(font_name_east_asian="宋体")
    model = Document(
        source_path=str(path),
        paragraphs=[
            Paragraph(
                index=0, text="x", role=Role.BODY, resolved_style=body_style,
            )
        ],
    )
    from papergroom.rules.applier import W_NS

    apply_ruleset(model, None, docx_doc)
    run = docx_doc.paragraphs[0].runs[0]
    rPr = run._element.find(f"{{{W_NS}}}rPr")
    rFonts = rPr.find(f"{{{W_NS}}}rFonts")
    assert rFonts is not None
    assert rFonts.get(f"{{{W_NS}}}eastAsia") == "宋体"
