"""Apply a SplitPlan to a Document model (in-place).

After applying, ``doc.paragraphs`` has a new length and new indices. The
paragraphs are re-indexed contiguously from 0. Each paragraph's
``original_index`` field traces it back to the original parsed document.
"""

from __future__ import annotations

from ..models import Document, Paragraph
from .models import SplitOperation, SplitPlan


def apply_plan_to_model(doc: Document, plan: SplitPlan) -> None:
    """Apply ``plan`` to ``doc`` in-place.

    After this call:
    - ``doc.paragraphs`` is re-indexed contiguously from 0
    - ``plan.final_paragraph_count`` is set
    - Each paragraph has ``original_index`` set
    """
    _init_original_indices(doc)

    for op in plan.operations:
        _apply_split(doc, op)

    _reindex(doc)
    plan.final_paragraph_count = len(doc.paragraphs)


def _init_original_indices(doc: Document) -> None:
    for p in doc.paragraphs:
        if p.original_index is None:
            p.original_index = p.index


def _apply_split(doc: Document, op: SplitOperation) -> None:
    paras = doc.paragraphs
    idx = op.paragraph_index
    if idx < 0 or idx >= len(paras):
        return

    original = paras[idx]

    if original.has_image or original.has_formula or original.has_table:
        return

    text = original.text
    positions = sorted(set(op.split_positions))
    positions = [p for p in positions if 0 < p < len(text)]
    if not positions:
        return

    pieces: list[str] = []
    prev = 0
    for pos in positions:
        pieces.append(text[prev:pos])
        prev = pos
    pieces.append(text[prev:])

    first_piece = pieces[0]
    original.text = first_piece
    original.is_empty = not first_piece.strip()

    orig_idx = (
        original.original_index
        if original.original_index is not None
        else original.index
    )

    new_paras: list[Paragraph] = []
    for piece in pieces[1:]:
        new_para = Paragraph(
            index=0,
            original_index=orig_idx,
            text=piece,
            style_hint=original.style_hint,
            has_image=False,
            has_table=False,
            has_formula=False,
            is_empty=not piece.strip(),
            original_pPr_xml=original.original_pPr_xml,
            role=original.role,
            confidence=original.confidence,
            resolved_style=None,
        )
        new_paras.append(new_para)

    paras[idx + 1 : idx + 1] = new_paras


def _reindex(doc: Document) -> None:
    for i, p in enumerate(doc.paragraphs):
        p.index = i
