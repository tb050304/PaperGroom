"""Build a SplitPlan by running all detectors and resolving overlaps."""

from __future__ import annotations

from typing import Callable

from ..models import Document
from .detect_merged_headings import detect_merged_headings
from .detect_merged_references import detect_merged_references
from .models import SplitOperation, SplitPlan

_ALL_DETECTORS = [
    detect_merged_references,
    detect_merged_headings,
]


def build_plan(
    doc: Document,
    detectors: list[Callable] | None = None,
) -> SplitPlan:
    """Run all detectors and produce an ordered SplitPlan.

    Args:
        doc: Original parsed document (not modified).
        detectors: List of detector functions. If None, use all built-in detectors.

    Returns:
        A SplitPlan with operations in execution order.
    """
    if detectors is None:
        detectors = _ALL_DETECTORS

    original_count = len(doc.paragraphs)

    # Collect ops from all detectors, keyed by original paragraph index.
    splits_by_para: dict[int, list[int]] = {}
    reasons_by_para: dict[int, list[str]] = {}

    for det in detectors:
        for op in det(doc):
            idx = op.paragraph_index
            if idx not in splits_by_para:
                splits_by_para[idx] = []
                reasons_by_para[idx] = []
            splits_by_para[idx].extend(op.split_positions)
            if op.reason:
                reasons_by_para[idx].append(op.reason)

    if not splits_by_para:
        return SplitPlan(
            operations=[],
            original_paragraph_count=original_count,
            final_paragraph_count=original_count,
        )

    # Build operations in original-index order, then convert to execution order.
    raw_ops: list[SplitOperation] = []
    for idx in sorted(splits_by_para.keys()):
        positions = sorted(set(splits_by_para[idx]))
        positions = [p for p in positions if p > 0]
        if positions:
            reasons = "; ".join(reasons_by_para.get(idx, []))
            raw_ops.append(
                SplitOperation(
                    paragraph_index=idx,
                    split_positions=positions,
                    reason=reasons,
                )
            )

    # Convert to execution order: each split adds N new paragraphs,
    # shifting all later indices up by N.
    shift = 0
    execution_ops: list[SplitOperation] = []
    for op in raw_ops:
        new_idx = op.paragraph_index + shift
        execution_ops.append(
            SplitOperation(
                paragraph_index=new_idx,
                split_positions=list(op.split_positions),
                reason=op.reason,
            )
        )
        shift += len(op.split_positions)

    plan = SplitPlan(
        operations=execution_ops,
        original_paragraph_count=original_count,
    )
    plan.final_paragraph_count = _compute_final_count(plan)
    return plan


def _compute_final_count(plan: SplitPlan) -> int:
    count = plan.original_paragraph_count
    for op in plan.operations:
        count += len(op.split_positions)
    return count
