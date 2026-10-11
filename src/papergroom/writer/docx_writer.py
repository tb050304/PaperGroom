"""Save the styled python-docx document to a .docx file.

The applier mutates the in-memory ``Document`` in place; this module is a
thin shim that re-opens the source file (to start from the original
bytes), applies styles, ensures track changes are off, and saves.

Keeping writer separate from applier lets us later add pre-save hooks
(e.g. rebuild TOC, sanitize metadata) without touching the applier.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from lxml import etree

from ..models import Document
from ..rules.applier import apply_ruleset

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def write_document(
    doc: Document,
    ruleset,
    output_path: str | Path,
) -> Path:
    """Open the source docx, apply styles, save to ``output_path``.

    In the new architecture, styles come from ``doc.paragraphs[i].resolved_style``
    (set by the AI labeler). ``ruleset`` is kept for backward compatibility
    but is not used.

    Args:
        doc: Parsed + labeled document model. ``doc.source_path`` is used
            as the starting point so we never modify the input in place.
        ruleset: Unused (kept for API compatibility). Pass None.
        output_path: Destination .docx path. Parent directory is created
            if missing.

    Returns:
        The resolved output path.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Re-open the source so we start from pristine bytes.
    docx_doc = DocxDocument(doc.source_path)

    apply_ruleset(doc, ruleset, docx_doc)

    _disable_track_changes(docx_doc)

    docx_doc.save(str(out))
    return out.resolve()


def _disable_track_changes(docx_doc: DocxDocument) -> None:
    """Remove ``w:trackChanges`` from settings.xml so saves are clean.

    When track changes is on, every style change is recorded as a
    revision, polluting the review stream. We strip it so the output is
    a clean "accepted" state.
    """
    settings = docx_doc.settings.element
    for tc in settings.findall(f"{{{W_NS}}}trackChanges"):
        settings.remove(tc)
