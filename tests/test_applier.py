"""Tests for the rule engine (schema, loader, applier).

Loader + schema: build a ruleset from YAML and from the built-in pack.
Applier: apply to a hand-built docx, then read it back to verify the
styles landed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document as DocxDocument
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from papergroom.models import Document, Paragraph, Role
from papergroom.rules import load_ruleset
from papergroom.rules.applier import apply_ruleset
from papergroom.rules.schema import ParagraphStyle, Ruleset, TableBorders


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


def test_apply_negative_first_line_indent_makes_a_hanging_indent(tmp_path: Path):
    """A negative first-line indent cancels the left indent on line one."""
    path, docx_doc = _build_docx_with_body(tmp_path)
    style = ParagraphStyle(
        font_size_pt=10.5,
        first_line_indent_chars=-2.0,
        left_indent_pt=21,
    )
    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(
                index=0,
                text="[1] 某文献.",
                role=Role.REFERENCE,
                resolved_style=style,
            )
        ],
    )

    apply_ruleset(model, None, docx_doc)

    pf = docx_doc.paragraphs[0].paragraph_format
    assert pf.first_line_indent == Pt(-21)  # 10.5pt × -2
    assert pf.left_indent == Pt(21)


def test_apply_is_idempotent(tmp_path: Path):
    """Applying the same style twice must change nothing the second time.

    The writer never applies twice today, but idempotence is the property that
    makes a re-run over already-formatted output safe — and a style written as
    an *addition* rather than a *replacement* would break it silently.
    """
    path, docx_doc = _build_docx_with_body(tmp_path)
    style = ParagraphStyle(
        font_size_pt=12,
        alignment="justify",
        first_line_indent_chars=2,
        font_name_east_asian="宋体",
        line_spacing=1.5,
        space_before_pt=6,
        space_after_pt=6,
    )
    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(index=0, text="First body paragraph.", role=Role.BODY, resolved_style=style),
            Paragraph(index=1, text="Second body paragraph.", role=Role.BODY, resolved_style=style),
        ],
    )

    apply_ruleset(model, None, docx_doc)
    once = docx_doc.paragraphs[0]._p.xml
    apply_ruleset(model, None, docx_doc)

    assert docx_doc.paragraphs[0]._p.xml == once


# ---------- tables ----------


def test_table_cells_get_the_table_text_style(tmp_path: Path):
    doc = DocxDocument()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "方法"
    table.cell(0, 1).text = "结果"
    path = tmp_path / "table.docx"
    doc.save(str(path))
    docx_doc = DocxDocument(str(path))

    ruleset = Ruleset(
        name="t",
        styles={
            "table": ParagraphStyle(alignment="center"),
            "table_text": ParagraphStyle(
                font_size_pt=10.5,
                font_name_east_asian="宋体",
                first_line_indent_chars=0,
            ),
        },
    )
    model = Document(source_path=str(path.resolve()), paragraphs=[])

    apply_ruleset(model, ruleset, docx_doc)

    assert docx_doc.tables[0].alignment == WD_TABLE_ALIGNMENT.CENTER
    cell_para = docx_doc.tables[0].cell(0, 0).paragraphs[0]
    assert cell_para.runs[0].font.size == Pt(10.5)


def _table_docx(tmp_path: Path) -> tuple[Path, DocxDocument]:
    doc = DocxDocument()
    table = doc.add_table(rows=2, cols=2)
    for r in range(2):
        for c in range(2):
            table.cell(r, c).text = f"r{r}c{c}"
    path = tmp_path / "table.docx"
    doc.save(str(path))
    return path, DocxDocument(str(path))


def _borders_by_edge(docx_doc: DocxDocument) -> dict:
    element = docx_doc.tables[0]._tbl.tblPr.find(qn("w:tblBorders"))
    assert element is not None
    return {child.tag.split("}")[-1]: child for child in element}


def test_three_line_table_borders(tmp_path: Path):
    path, docx_doc = _table_docx(tmp_path)
    ruleset = Ruleset(
        name="t",
        styles={},
        table_borders=TableBorders(
            style="three_line", outer_width_pt=1.5, header_width_pt=0.75
        ),
    )
    model = Document(source_path=str(path.resolve()), paragraphs=[])

    apply_ruleset(model, ruleset, docx_doc)

    edges = _borders_by_edge(docx_doc)
    assert edges["top"].get(qn("w:val")) == "single"
    assert edges["top"].get(qn("w:sz")) == "12"  # 1.5pt in eighths
    assert edges["bottom"].get(qn("w:sz")) == "12"
    for edge in ("left", "right", "insideH", "insideV"):
        assert edges[edge].get(qn("w:val")) == "nil"

    # The rule under the header row lives on the cells, not the table.
    header = docx_doc.tables[0].rows[0].cells[0]
    tc_borders = header._tc.tcPr.find(qn("w:tcBorders"))
    assert tc_borders is not None
    assert tc_borders.find(qn("w:bottom")).get(qn("w:sz")) == "6"  # 0.75pt


def test_no_borders_removes_them(tmp_path: Path):
    path, docx_doc = _table_docx(tmp_path)
    ruleset = Ruleset(name="t", styles={}, table_borders=TableBorders(style="none"))
    model = Document(source_path=str(path.resolve()), paragraphs=[])

    apply_ruleset(model, ruleset, docx_doc)

    edges = _borders_by_edge(docx_doc)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        assert edges[edge].get(qn("w:val")) == "nil"


def test_keep_leaves_borders_alone(tmp_path: Path):
    path, docx_doc = _table_docx(tmp_path)
    ruleset = Ruleset(name="t", styles={}, table_borders=TableBorders(style="keep"))
    model = Document(source_path=str(path.resolve()), paragraphs=[])

    apply_ruleset(model, ruleset, docx_doc)

    assert docx_doc.tables[0]._tbl.tblPr.find(qn("w:tblBorders")) is None


def test_tables_are_untouched_without_table_styles(tmp_path: Path):
    doc = DocxDocument()
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "内容"
    path = tmp_path / "table.docx"
    doc.save(str(path))
    docx_doc = DocxDocument(str(path))
    before = docx_doc.tables[0].alignment

    model = Document(source_path=str(path.resolve()), paragraphs=[])
    apply_ruleset(model, Ruleset(name="t", styles={}), docx_doc)

    assert docx_doc.tables[0].alignment == before


# ---------- Word built-in styles (--word-styles) ----------


def test_word_styles_maps_headings_by_style_id(tmp_path: Path):
    """IDs, not localized names — this must work on a Chinese Word install."""
    path, docx_doc = _build_docx_with_body(tmp_path)
    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(
                index=0,
                text="1 研究背景",
                role=Role.TITLE_L1,
                resolved_style=ParagraphStyle(font_size_pt=16, bold=True),
            ),
            Paragraph(
                index=1,
                text="正文段落。",
                role=Role.BODY,
                resolved_style=ParagraphStyle(font_size_pt=12),
            ),
        ],
    )

    apply_ruleset(model, None, docx_doc, word_styles=True)

    assert docx_doc.paragraphs[0].style.style_id == "Heading1"
    assert docx_doc.paragraphs[1].style.style_id != "Heading1"


def test_word_style_is_found_by_name_not_by_id(tmp_path: Path):
    """Real documents do not always use Word's own style ids.

    The sample thesis this project was developed against defines Normal as
    "a" and Heading 1 as "1" — a converter, not Word, produced it. Looking up
    "Heading1" would silently do nothing.
    """
    path, docx_doc = _build_docx_with_body(tmp_path)
    for style in docx_doc.styles.element.findall(qn("w:style")):
        if style.get(qn("w:styleId")) == "Heading1":
            style.set(qn("w:styleId"), "1")

    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(
                index=0,
                text="1 研究背景",
                role=Role.TITLE_L1,
                resolved_style=ParagraphStyle(font_size_pt=16),
            )
        ],
    )

    apply_ruleset(model, None, docx_doc, word_styles=True)

    assert docx_doc.paragraphs[0].style.style_id == "1"


def test_without_word_styles_no_style_is_assigned(tmp_path: Path):
    path, docx_doc = _build_docx_with_body(tmp_path)
    before = docx_doc.paragraphs[0].style.style_id
    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(
                index=0,
                text="1 研究背景",
                role=Role.TITLE_L1,
                resolved_style=ParagraphStyle(font_size_pt=16),
            )
        ],
    )

    apply_ruleset(model, None, docx_doc)

    assert docx_doc.paragraphs[0].style.style_id == before


def test_word_styles_neutralise_the_theme_colour(tmp_path: Path):
    """The default Heading 1 is blue; a thesis heading should not be."""
    path, docx_doc = _build_docx_with_body(tmp_path)
    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(
                index=0,
                text="1 研究背景",
                role=Role.TITLE_L1,
                resolved_style=ParagraphStyle(font_size_pt=16, bold=True),
            )
        ],
    )

    apply_ruleset(model, None, docx_doc, word_styles=True)

    assert docx_doc.paragraphs[0].runs[0].font.color.rgb == RGBColor(0, 0, 0)


def test_word_styles_respect_an_explicit_colour(tmp_path: Path):
    path, docx_doc = _build_docx_with_body(tmp_path)
    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(
                index=0,
                text="1 研究背景",
                role=Role.TITLE_L1,
                resolved_style=ParagraphStyle(font_size_pt=16, color_hex="FF0000"),
            )
        ],
    )

    apply_ruleset(model, None, docx_doc, word_styles=True)

    assert docx_doc.paragraphs[0].runs[0].font.color.rgb == RGBColor(0xFF, 0, 0)


def test_a_missing_word_style_is_not_invented(tmp_path: Path):
    """Never reference a style the document does not define."""
    path, docx_doc = _build_docx_with_body(tmp_path)
    for style in list(docx_doc.styles.element.findall(qn("w:style"))):
        if style.get(qn("w:styleId")) == "Heading1":
            docx_doc.styles.element.remove(style)
    before = docx_doc.paragraphs[0].style.style_id

    model = Document(
        source_path=str(path.resolve()),
        paragraphs=[
            Paragraph(
                index=0,
                text="1 研究背景",
                role=Role.TITLE_L1,
                resolved_style=ParagraphStyle(font_size_pt=16),
            )
        ],
    )

    apply_ruleset(model, None, docx_doc, word_styles=True)

    assert docx_doc.paragraphs[0].style.style_id == before


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
