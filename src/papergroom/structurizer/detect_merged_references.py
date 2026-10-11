"""Detect paragraphs containing multiple concatenated reference entries.

Patterns handled:
- "[1] xxx [2] yyy [3] zzz" — multiple refs in one paragraph
- "参考文献：[1] xxx" — the refs header concatenated with the first entry
- Full-width brackets: "［1］xxx［2］yyy"

Split happens before each ``[n]`` marker after the first one.
"""

from __future__ import annotations

import re

from ..models import Document
from .models import SplitOperation

# Match reference markers: [1], ［2］, [123], etc.
_REF_MARKER = re.compile(r"[\[［]\s*\d+\s*[\]］]")

# "参考文献：" or "References:" immediately followed by [n]
_REF_HEADER = re.compile(
    r"^\s*(参考文献|References|REFERENCES)\s*[:：]\s*(?=[\[［])",
    re.IGNORECASE,
)


def detect_merged_references(doc: Document) -> list[SplitOperation]:
    """Detect paragraphs with multiple references and propose splits.

    Operates on original paragraph indices.
    """
    ops: list[SplitOperation] = []

    for p in doc.paragraphs:
        if p.is_empty or p.has_image or p.has_formula or p.has_table:
            continue

        text = p.text
        if not text:
            continue

        markers = list(_REF_MARKER.finditer(text))

        if len(markers) >= 2:
            # Multiple references → split before each marker after the first.
            positions = [m.start() for m in markers[1:]]
            ops.append(
                SplitOperation(
                    paragraph_index=p.index,
                    split_positions=positions,
                    reason=f"merged_references: {len(markers)} refs",
                )
            )
            continue

        # Single ref preceded by a header like "参考文献："
        if len(markers) == 1:
            header_match = _REF_HEADER.match(text)
            if header_match:
                header_end = header_match.end()
                if header_end <= markers[0].start():
                    ops.append(
                        SplitOperation(
                            paragraph_index=p.index,
                            split_positions=[header_end],
                            reason="merged_references: header + first ref",
                        )
                    )

    return ops
