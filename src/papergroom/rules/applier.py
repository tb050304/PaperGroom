"""Apply resolved styles to a python-docx document.

In the new architecture, the AI labeler decides per-paragraph styles
directly (stored on ``Paragraph.resolved_style``). The applier simply
walks the document and applies each paragraph's resolved style.

Key principle: ONLY properties explicitly set by the AI are changed.
All other properties keep the original document formatting.
"""

from __future__ import annotations

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from lxml import etree

from ..models import Document, Paragraph, ParagraphStyle, Role

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_ALIGN_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def apply_ruleset(
    doc: Document, ruleset, docx_doc: DocxDocument
) -> None:
    """Apply resolved styles to ``docx_doc`` based on the labeled ``doc``.

    ``ruleset`` is kept for backward compatibility but is NOT used in the
    new flow — styles come from ``para.resolved_style``.

    Mutates ``docx_doc`` in place. Caller saves it afterwards.
    Paragraphs in ``doc.paragraphs`` are matched to ``docx_doc.paragraphs``
    by index.
    """
    docx_paragraphs = docx_doc.paragraphs
    for para_model in doc.paragraphs:
        if para_model.index >= len(docx_paragraphs):
            break
        para_docx = docx_paragraphs[para_model.index]

        style = para_model.resolved_style

        # No resolved style → change nothing (preserve original formatting).
        if style is None or style.is_empty():
            continue

        # Protected: formulas only get outer paragraph style, no run edits.
        if para_model.has_formula:
            _apply_paragraph_only(para_docx, style)
            continue

        _apply_full(para_docx, style)


def _apply_full(para, style: ParagraphStyle) -> None:
    """Apply paragraph + run properties from ``style``."""
    _apply_paragraph_only(para, style)

    for run in para.runs:
        _apply_run(run, style)


def _apply_paragraph_only(para, style: ParagraphStyle) -> None:
    """Apply only paragraph-level properties (alignment, spacing, indent)."""
    pf = para.paragraph_format

    if style.alignment is not None:
        para.alignment = _ALIGN_MAP[style.alignment]

    if style.line_spacing is not None:
        pf.line_spacing = style.line_spacing

    if style.space_before_pt is not None:
        pf.space_before = Pt(style.space_before_pt)

    if style.space_after_pt is not None:
        pf.space_after = Pt(style.space_after_pt)

    if style.first_line_indent_chars is not None:
        char_pt = style.font_size_pt if style.font_size_pt is not None else 12.0
        pf.first_line_indent = Pt(char_pt * style.first_line_indent_chars)

    if style.left_indent_pt is not None:
        pf.left_indent = Pt(style.left_indent_pt)


def _apply_run(run, style: ParagraphStyle) -> None:
    """Apply font name, size, weight, italic, color to a single run."""
    if style.font_size_pt is not None:
        run.font.size = Pt(style.font_size_pt)
    if style.bold is not None:
        run.font.bold = style.bold
    if style.italic is not None:
        run.font.italic = style.italic
    if style.color_hex is not None:
        run.font.color.rgb = RGBColor.from_string(style.color_hex)

    if style.font_name is not None:
        run.font.name = style.font_name

    if style.font_name_east_asian is not None:
        _set_east_asian_font(run, style.font_name_east_asian)


def _set_east_asian_font(run, font_name: str) -> None:
    """Set ``w:rFonts/@w:eastAsia`` on the run's ``rPr``.

    python-docx's ``run.font.name`` only writes ``w:ascii`` and
    ``w:hAnsi``; East Asian text reads ``w:eastAsia``.
    """
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(f"{{{W_NS}}}rFonts")
    if rFonts is None:
        rFonts = etree.SubElement(rPr, f"{{{W_NS}}}rFonts")
    rFonts.set(f"{{{W_NS}}}eastAsia", font_name)
    if rFonts.get(f"{{{W_NS}}}ascii") is None:
        rFonts.set(f"{{{W_NS}}}ascii", font_name)
    if rFonts.get(f"{{{W_NS}}}hAnsi") is None:
        rFonts.set(f"{{{W_NS}}}hAnsi", font_name)
