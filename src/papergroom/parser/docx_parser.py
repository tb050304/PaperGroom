"""Parse a .docx file into PaperGroom's intermediate ``Document`` model.

We use python-docx for paragraph iteration and lxml directly on the
underlying ``<w:p>`` element to detect protected objects (images, tables,
formulas) and to capture the original ``<w:pPr>`` XML for the writer.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from lxml import etree

from ..models import Document, Paragraph

# WordprocessingML namespace
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
# DrawingML namespace
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
# Office Math namespace
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

_NS = {"w": W_NS, "wp": WP_NS, "m": M_NS}


def parse_document(source_path: str | Path) -> Document:
    """Open a .docx file and return a parsed :class:`Document`.

    The original python-docx object is discarded after parsing; the writer
    will re-open the file from ``source_path`` to apply styles.

    Args:
        source_path: Path to the input .docx file.

    Returns:
        A :class:`Document` with ordered :class:`Paragraph` entries. Every
        paragraph starts with ``role=UNKNOWN``; the labeler fills them in.
    """
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Input docx not found: {source}")
    if source.suffix.lower() != ".docx":
        raise ValueError(f"Only .docx files are supported, got: {source.name}")

    doc = DocxDocument(str(source))

    paragraphs: list[Paragraph] = []
    for idx, para in enumerate(doc.paragraphs):
        p_xml = para._p  # underlying lxml element

        text = para.text or ""
        has_image = _paragraph_has_image(p_xml)
        has_formula = _paragraph_has_math(p_xml)
        has_hyperlink = _paragraph_has_hyperlink(p_xml)
        pPr_xml = _serialize_pPr(p_xml)
        style_hint = _style_hint(para)
        # A paragraph is "empty" when it has no text AND no embedded object
        # (image / formula). Such paragraphs are layout placeholders
        # (blank lines, vertical spacing) and carry no semantic signal for
        # the AI — we skip labeling them to save tokens and avoid noise.
        is_empty = not text.strip() and not has_image and not has_formula

        paragraphs.append(
            Paragraph(
                index=idx,
                text=text,
                style_hint=style_hint,
                has_image=has_image,
                has_formula=has_formula,
                has_hyperlink=has_hyperlink,
                is_empty=is_empty,
                original_pPr_xml=pPr_xml,
                source_index=idx,
            )
        )

    # Note: python-docx's document.paragraphs excludes table contents by design.
    # Tables are skipped here; the applier also iterates tables separately so
    # table-internal paragraphs get style applied via the writer. The
    # Paragraph list above is the "main body" stream only.
    # TODO(Stage 2): emit table blocks as Paragraph entries with has_table=True
    # so the labeler can see them and a caption can attach to them.

    return Document(source_path=str(source.resolve()), paragraphs=paragraphs)


def _paragraph_has_image(p_xml) -> bool:
    """True if the paragraph element contains a ``w:drawing``.

    Inline shapes (``wp:inline``) and anchored shapes (``wp:anchor``) both
    live inside ``w:drawing``.
    """
    return p_xml.find(f".//{{{W_NS}}}drawing") is not None


def _paragraph_has_math(p_xml) -> bool:
    """True if the paragraph contains an ``m:oMath`` (OMML) element."""
    return p_xml.find(f".//{{{M_NS}}}oMath") is not None


def _paragraph_has_hyperlink(p_xml) -> bool:
    """True if the paragraph contains a ``w:hyperlink``.

    Hyperlink text lives inside a nested element rather than in a direct
    ``w:r`` child, so the character offsets the segmenter computes would not
    line up with the runs. Paragraphs carrying one are never split.
    """
    return p_xml.find(f".//{{{W_NS}}}hyperlink") is not None


def _serialize_pPr(p_xml) -> str | None:
    """Serialize the ``<w:pPr>`` child to a string, if present.

    Kept so the writer can restore original paragraph properties when the
    ruleset asks to preserve them. Returns None if there is no ``<w:pPr>``.
    """
    pPr = p_xml.find(f"w:pPr", _NS)
    if pPr is None:
        return None
    return etree.tostring(pPr, encoding="unicode")


def _style_hint(para) -> str | None:
    """Read the ``w:pStyle/@w:val`` value, if any (e.g. "Heading1")."""
    style = para.style
    if style is None or not style.name:
        return None
    # python-docx exposes the style name; the underlying w:pStyle/@w:val is
    # the styleId, which is more stable across localizations.
    pPr = para._p.find(f"w:pPr", _NS)
    if pPr is None:
        return None
    pStyle = pPr.find(f"w:pStyle", _NS)
    if pStyle is None:
        return None
    val = pStyle.get(f"{{{W_NS}}}val")
    return val
