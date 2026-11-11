"""Editable label files: export what was decided, correct it, re-run.

The report shows what the tool did; this is how a person fixes it. Export
produces a small JSON file, the role of each paragraph on one line, which can
be edited by hand and passed back in. Paragraphs with an override are never
sent to the model, so a correction is also a cost saving.

The file records the paragraph text alongside the role and is checked on
import. If the text does not match, the file is stale — probably exported
from a different document or an earlier version of it — and applying it would
label the wrong paragraphs. That is a hard error, not a warning.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Document, Role


class LabelsError(ValueError):
    """The labels file is unreadable, invalid, or does not match the document."""


def export_labels(doc: Document, path: str | Path) -> Path:
    """Write an editable labels file for ``doc``. Returns the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "source": doc.source_path,
                "paragraphs": [
                    {"index": p.index, "role": p.role.value, "text": p.text}
                    for p in doc.paragraphs
                    if not p.is_empty
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out


def load_labels(path: str | Path, doc: Document) -> dict[int, Role]:
    """Read overrides from ``path``, validated against ``doc``.

    Raises:
        LabelsError: unreadable file, unknown role, out-of-range index, or
            text that does not match this document.
    """
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except OSError as e:
        raise LabelsError(f"cannot read {source}: {e}") from e
    except json.JSONDecodeError as e:
        raise LabelsError(f"{source} is not valid JSON: {e}") from e

    entries = data.get("paragraphs") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise LabelsError(f"{source} must contain a 'paragraphs' list")

    by_index = {p.index: p for p in doc.paragraphs}
    overrides: dict[int, Role] = {}

    for entry in entries:
        if not isinstance(entry, dict):
            raise LabelsError(f"{source}: expected objects, got {entry!r}")

        index = entry.get("index")
        if not isinstance(index, int):
            raise LabelsError(f"{source}: entry has no integer index: {entry!r}")

        paragraph = by_index.get(index)
        if paragraph is None:
            raise LabelsError(
                f"{source}: paragraph {index} does not exist in this document "
                f"(it has {len(doc.paragraphs)})"
            )

        role_name = entry.get("role")
        try:
            role = Role(role_name)
        except ValueError as e:
            valid = ", ".join(r.value for r in Role)
            raise LabelsError(
                f"{source}: paragraph {index} has unknown role {role_name!r}. "
                f"Valid roles: {valid}"
            ) from e

        expected = entry.get("text")
        if expected is not None and expected.strip() != paragraph.text.strip():
            raise LabelsError(
                f"{source} does not match this document at paragraph {index}:\n"
                f"  file: {expected[:70]!r}\n"
                f"  doc : {paragraph.text[:70]!r}\n"
                "Re-export the labels for this document."
            )

        overrides[index] = role

    return overrides
