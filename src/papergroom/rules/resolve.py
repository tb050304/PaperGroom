"""Turn labeled roles into concrete styles.

The last step before writing: each paragraph's role is looked up in the
ruleset and the resulting style attached. Deterministic by construction — the
same document and the same ruleset always produce the same styles, which is
what makes the output reproducible and the applier testable.

This is the half of the design that the AI deliberately does not do. The
labeler answers "what is this paragraph?"; the ruleset answers "so what
should it look like?". Keeping them apart is the whole point.
"""

from __future__ import annotations

from ..models import Document
from .schema import Ruleset


def resolve_styles(doc: Document, ruleset: Ruleset) -> None:
    """Attach each paragraph's style from ``ruleset``, in place.

    A role the ruleset does not mention resolves to an empty style, which the
    applier reads as "change nothing". A ruleset that is silent about a role
    therefore leaves those paragraphs exactly as they were — the safe default.
    """
    for para in doc.paragraphs:
        para.resolved_style = ruleset.style_for(para.role.value)
