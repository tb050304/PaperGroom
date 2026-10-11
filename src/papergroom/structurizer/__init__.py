"""Structurizer: split merged paragraphs before AI labeling.

Detects paragraphs where multiple semantic units are concatenated
(heading+body, multiple references, etc.) and splits them so each
resulting paragraph contains exactly one unit.

Public API:
    structurize_document(doc) -> SplitPlan
        Detect and apply splits to ``doc`` in place.
        Returns the plan (also stored on doc.restructure_plan).
"""

from __future__ import annotations

from ..models import Document
from .apply_model import apply_plan_to_model
from .models import SplitPlan
from .plan_builder import build_plan


def structurize_document(doc: Document) -> SplitPlan:
    """Detect merged paragraphs and split them.

    Applies the split plan to the Document model in place.
    The plan is also stored on ``doc.restructure_plan`` so the writer
    can apply the same splits to the docx XML.

    Args:
        doc: Parsed document. Will be modified in place.

    Returns:
        The SplitPlan that was applied.
    """
    plan = build_plan(doc)
    if not plan.is_empty():
        apply_plan_to_model(doc, plan)

    doc.restructure_plan = plan
    return plan


__all__ = [
    "structurize_document",
    "SplitPlan",
]
