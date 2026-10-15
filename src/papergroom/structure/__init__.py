"""Structure recovery: turn flat paragraphs into one-semantic-unit paragraphs.

The target documents — a paper drafted by an LLM and pasted into Word, or
converted from PDF/HTML — arrive with their paragraph structure already
destroyed: a heading and its body merged into one paragraph, several
bibliography entries merged into one, a section word glued to its content.
Styling such a paragraph is wrong however it is labelled, because the
paragraph is not one thing.

This package fixes the structure before any styling decision is made.

Public API::

    structurize(doc) -> Document     split merged paragraphs, in place
    segment_text(text) -> [Segment]  the pure text rule, for testing
"""

from __future__ import annotations

from ..models import Document, Paragraph
from .segmenter import Segment, segment_text

__all__ = ["structurize", "segment_text", "Segment"]

# Paragraphs carrying one of these are never split: character offsets become
# ambiguous once text lives inside a drawing, an equation, or a hyperlink,
# and a wrong cut corrupts the object. Must stay in sync with
# ``structure.apply._is_splittable``, which enforces the same rule on the XML
# — if they disagree, the paragraph count drifts out of sync and the writer's
# index mapping breaks.
_UNSPLITTABLE_FLAGS = ("has_image", "has_formula", "has_hyperlink")


def structurize(doc: Document) -> Document:
    """Split merged paragraphs in ``doc`` in place, and return it.

    One input paragraph may become several. Afterwards ``doc.paragraphs``
    holds exactly one semantic unit per entry, and ``doc.splits`` records the
    character ranges so the writer can replay the same split on the docx XML.
    """
    out: list[Paragraph] = []
    splits: dict[int, list[tuple[int, int]]] = {}

    for para in doc.paragraphs:
        segments = segment_text(para.text)
        source_index = para.source_index if para.source_index is not None else para.index

        if len(segments) <= 1 or any(getattr(para, f) for f in _UNSPLITTABLE_FLAGS):
            # Nothing to do. Keep the paragraph's own text rather than the
            # segment's trimmed copy, so the model still matches the docx.
            out.append(
                para.model_copy(
                    update={
                        "index": len(out),
                        "source_index": source_index,
                        "role_hint": segments[0].role_hint,
                    }
                )
            )
            continue

        splits[source_index] = [(s.start, s.end) for s in segments]
        for seg in segments:
            out.append(
                para.model_copy(
                    update={
                        "index": len(out),
                        "text": seg.text,
                        "source_index": source_index,
                        "role_hint": seg.role_hint,
                    }
                )
            )

    doc.paragraphs = out
    doc.splits = splits
    return doc
