"""Data models for the structurizer.

A :class:`SplitPlan` describes where to split paragraphs so that each
resulting paragraph contains one semantic unit (one heading, one body
paragraph, one reference, etc.).

Operations are stored in **execution order**: each operation's
``paragraph_index`` refers to the current state of the document (after
all previous operations have been applied).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SplitOperation(BaseModel):
    """Split one paragraph into N+1 pieces at given character positions.

    ``split_positions`` are 0-indexed character offsets into the paragraph's
    concatenated text, sorted ascending. Each offset is the first character
    of a *new* paragraph. For example, splitting "abcdef" at [2, 4] yields
    ["ab", "cd", "ef"].

    New paragraphs inherit the original paragraph's properties (pPr, style
    hint, etc.).
    """

    paragraph_index: int
    split_positions: list[int] = Field(..., min_length=1)
    reason: str = ""


class SplitPlan(BaseModel):
    """A plan for splitting merged paragraphs in a document.

    Operations are applied in order. Each operation's indices refer to the
    *current* state (after all prior operations).
    """

    operations: list[SplitOperation] = Field(default_factory=list)
    original_paragraph_count: int = 0
    final_paragraph_count: int | None = None

    def is_empty(self) -> bool:
        return len(self.operations) == 0
