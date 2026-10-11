"""Load formatting rules text for the AI labeler.

Rules are plain text / markdown that the AI reads and interprets. This
module provides:
- ``load_default_rules()``: the built-in standard thesis rules.
- ``load_rules_text(path)``: load a user-provided rules file (.txt/.md).
- ``resolve_rules_text(rules_arg)``: if ``rules_arg`` is a path, load it;
  otherwise fall back to the default rules.
"""

from __future__ import annotations

from pathlib import Path

# Path to the built-in default thesis rules markdown file.
_DEFAULT_RULES_PATH = Path(__file__).parent / "default_thesis_rules.md"


def load_default_rules() -> str:
    """Return the built-in standard thesis formatting rules text."""
    return _DEFAULT_RULES_PATH.read_text(encoding="utf-8")


def load_rules_text(path: str | Path) -> str:
    """Load a user-provided rules text file (.txt / .md)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Rules file not found: {p}")
    return p.read_text(encoding="utf-8")


def resolve_rules_text(rules_arg: str | None) -> tuple[str, str]:
    """Resolve the rules text and a human-readable source name.

    Args:
        rules_arg: If a path to an existing file, load it. Otherwise
            (None or a name that isn't a file), use the built-in default.

    Returns:
        (rules_text, source_name) where source_name is either the file
        path or "default_thesis".
    """
    if rules_arg:
        p = Path(rules_arg)
        if p.exists() and p.is_file():
            return load_rules_text(p), str(p)
    return load_default_rules(), "default_thesis"
