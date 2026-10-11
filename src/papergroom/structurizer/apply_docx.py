"""Apply a SplitPlan to a python-docx document's XML tree.

Splits ``<w:p>`` elements at the character level, preserving run-level
formatting (font, bold, italic, color, etc.).

The same ``SplitPlan`` applied to the Document model must be applied here
to keep paragraph indices in sync.
"""

from __future__ import annotations

from copy import deepcopy

from docx import Document as DocxDocument
from lxml import etree

from .models import SplitOperation, SplitPlan

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"

W = f"{{{W_NS}}}"


def apply_plan_to_docx(docx_doc: DocxDocument, plan: SplitPlan) -> None:
    """Apply ``plan`` to ``docx_doc`` in-place by manipulating its XML."""
    if plan.is_empty():
        return

    body = docx_doc.element.body

    for op in plan.operations:
        _apply_split(body, op)


def _apply_split(body, op: SplitOperation) -> None:
    all_p = _get_paragraphs(body)
    idx = op.paragraph_index
    if idx < 0 or idx >= len(all_p):
        return

    p_elem = all_p[idx]

    if _paragraph_has_objects(p_elem):
        return

    text = _paragraph_text(p_elem)
    positions = sorted(set(op.split_positions))
    positions = [p for p in positions if 0 < p < len(text)]
    if not positions:
        return

    # Process splits from right to left so the original keeps shrinking.
    new_elements: list = []
    for pos in reversed(positions):
        new_p = _split_paragraph_at_char(p_elem, pos)
        if new_p is not None:
            new_elements.append(new_p)

    # Insert new paragraphs after the original in correct left-to-right order.
    anchor = p_elem
    for new_p in reversed(new_elements):
        anchor.addnext(new_p)
        anchor = new_p


def _split_paragraph_at_char(p_elem, char_pos: int):
    """Split a ``<w:p>`` at character position ``char_pos``.

    Returns the new paragraph (right half), or None if the split can't be done.
    """
    runs_info = _build_run_info(p_elem)

    run_idx, offset_in_run = _find_run_at_offset(runs_info, char_pos)
    if run_idx is None:
        return None

    target_run_info = runs_info[run_idx]
    if target_run_info.is_non_text:
        return None

    run_elem = target_run_info.element
    t_elem = run_elem.find(f"{W}t")
    if t_elem is None or t_elem.text is None:
        return None

    full_text = t_elem.text
    left_text = full_text[:offset_in_run]
    right_text = full_text[offset_in_run:]

    t_elem.text = left_text

    # Create right-half run as a deep copy (preserves rPr).
    right_run = deepcopy(run_elem)
    right_t = right_run.find(f"{W}t")
    if right_t is not None:
        right_t.text = right_text
        if right_text and (right_text[0] == " " or right_text[-1] == " "):
            right_t.set(f"{{{XML_NS}}}space", "preserve")

    # Build new paragraph with copy of pPr.
    new_p = _make_new_paragraph(p_elem)
    new_p.append(right_run)

    # Move all runs after the target run from old to new paragraph.
    all_children = list(p_elem)
    target_index = all_children.index(run_elem)
    for child in all_children[target_index + 1 :]:
        p_elem.remove(child)
        new_p.append(child)

    return new_p


class _RunInfo:
    def __init__(self, element, start: int, end: int, *, is_non_text: bool):
        self.element = element
        self.start = start
        self.end = end
        self.is_non_text = is_non_text


def _build_run_info(p_elem) -> list:
    runs_info = []
    offset = 0
    for r in p_elem.findall(f"{W}r"):
        t = r.find(f"{W}t")
        if t is None or t.text is None:
            runs_info.append(_RunInfo(r, offset, offset, is_non_text=True))
            continue
        text_len = len(t.text)
        runs_info.append(_RunInfo(r, offset, offset + text_len, is_non_text=False))
        offset += text_len
    return runs_info


def _find_run_at_offset(runs_info, char_pos: int):
    for i, info in enumerate(runs_info):
        if info.is_non_text:
            continue
        if info.start <= char_pos < info.end:
            return i, char_pos - info.start
    return None, None


def _get_paragraphs(body):
    return body.findall(f"{W}p")


def _paragraph_text(p_elem) -> str:
    parts = []
    for t in p_elem.findall(f".//{W}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def _paragraph_has_objects(p_elem) -> bool:
    if p_elem.find(f".//{W}drawing") is not None:
        return True
    for elem in p_elem.iter():
        if etree.QName(elem).localname == "oMath":
            return True
    return False


def _make_new_paragraph(source_p_elem):
    new_p = etree.Element(f"{W}p")
    pPr = source_p_elem.find(f"{W}pPr")
    if pPr is not None:
        new_p.append(deepcopy(pPr))
    return new_p
