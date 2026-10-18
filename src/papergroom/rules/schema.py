"""Schema for a formatting ruleset, and the rules for combining two of them.

A ruleset maps a role to the style its paragraphs should get. Layering is how
"your rules win" works: a user ruleset declares ``extends: standard_thesis``
and then overrides only the fields it cares about. Merge granularity is
**role → field**, so setting one font size changes that font size and inherits
everything else.

Two consequences worth stating, because both are load-bearing:

* A field left ``None`` means "do not change this property in the document".
  The same value means "inherit it" during a merge. The merge resolves first,
  so by the time the applier sees a style, ``None`` unambiguously means
  "leave the document alone".
* There is no way to *unset* an inherited value. A user who wants to stop the
  base ruleset from setting, say, ``space_before_pt`` has to set a value of
  their own. Booleans can be turned off (``bold: false``); numeric and text
  fields cannot. Doing better would need a third state, which is not worth the
  confusion it creates.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..models import ParagraphStyle


class Ruleset(BaseModel):
    """A loaded ruleset: per-role styles, optionally extending another.

    ``extends`` is resolved at load time (see :mod:`papergroom.rules.loader`)
    and is ``None`` on a ruleset returned from the loader. The ``styles`` of a
    loaded ruleset are therefore complete for every role it knows about.

    Unknown keys are rejected: a misspelled role or property in a custom
    ruleset should fail loudly, not be silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: int = 1
    description: str | None = None
    extends: str | None = None
    styles: dict[str, ParagraphStyle] = Field(default_factory=dict)

    def style_for(self, role_name: str) -> ParagraphStyle:
        """Return the style for a role, or an empty style if unlisted.

        An empty style means "change nothing", which is the safe default: a
        ruleset that is silent about a role leaves those paragraphs exactly as
        they were.
        """
        role_style = self.styles.get(role_name)
        if role_style is None:
            return ParagraphStyle()
        return role_style.model_copy()


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def merge_styles(base: ParagraphStyle | None, overlay: ParagraphStyle) -> ParagraphStyle:
    """Combine two styles, field by field, with ``overlay`` winning.

    A property is taken from ``overlay`` when it is set there and inherited
    from ``base`` otherwise.
    """
    if base is None:
        return overlay.model_copy()

    merged = base.model_dump()
    for name, value in overlay.model_dump().items():
        if value is not None:
            merged[name] = value
    return ParagraphStyle(**merged)


def merge_rulesets(base: Ruleset, overlay: Ruleset) -> Ruleset:
    """Layer ``overlay`` on top of ``base``; return a fully resolved ruleset.

    The result keeps the overlay's identity (name, version, description) but
    carries the merged styles and no unresolved ``extends``.
    """
    styles = {role: style.model_copy() for role, style in base.styles.items()}
    for role, style in overlay.styles.items():
        styles[role] = merge_styles(styles.get(role), style)
    return overlay.model_copy(update={"styles": styles, "extends": None})
