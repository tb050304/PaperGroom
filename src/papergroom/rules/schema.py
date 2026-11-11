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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import ParagraphStyle

__all__ = [
    "PAGE_SIZES_CM",
    "PageSetup",
    "Ruleset",
    "TableBorders",
    "merge_rulesets",
    "merge_styles",
]


# Paper sizes in centimetres. ``size`` is a convenience; explicit width/height
# override it.
PAGE_SIZES_CM: dict[str, tuple[float, float]] = {
    "a4": (21.0, 29.7),
    "a3": (29.7, 42.0),
    "letter": (21.59, 27.94),
    "legal": (21.59, 35.56),
}


class PageSetup(BaseModel):
    """Paper size and margins, in centimetres.

    Every field is optional and a field left None is not changed. ``size``
    sets width and height; explicit ``width_cm`` / ``height_cm`` win over it.
    """

    model_config = ConfigDict(extra="forbid")

    size: str | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    top_cm: float | None = None
    bottom_cm: float | None = None
    left_cm: float | None = None
    right_cm: float | None = None
    gutter_cm: float | None = None

    @field_validator("size")
    @classmethod
    def _known_size(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip().lower()
        if normalised not in PAGE_SIZES_CM:
            raise ValueError(
                f"size must be one of {sorted(PAGE_SIZES_CM)}, got {value!r}"
            )
        return normalised

    @field_validator(
        "width_cm", "height_cm", "top_cm", "bottom_cm", "left_cm", "right_cm", "gutter_cm"
    )
    @classmethod
    def _sane_length(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 60:
            raise ValueError(f"page length must be between 0 and 60cm, got {value}")
        return value


class TableBorders(BaseModel):
    """How table borders are drawn.

    ``keep`` leaves the source document's borders alone (the default, so a
    ruleset that says nothing here changes nothing). ``none`` removes them.
    ``three_line`` draws a 三线表 — the usual Chinese thesis requirement: a
    rule above the table, one below the header row, one below the table, and
    nothing vertical.
    """

    model_config = ConfigDict(extra="forbid")

    style: str = "keep"
    outer_width_pt: float = 1.5
    header_width_pt: float = 0.75

    @field_validator("style")
    @classmethod
    def _known_style(cls, value: str) -> str:
        allowed = {"keep", "none", "three_line"}
        if value not in allowed:
            raise ValueError(f"style must be one of {sorted(allowed)}, got {value!r}")
        return value

    @field_validator("outer_width_pt", "header_width_pt")
    @classmethod
    def _sane_width(cls, value: float) -> float:
        if not 0 < value <= 20:
            raise ValueError(f"border width must be between 0 and 20pt, got {value}")
        return value


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
    # None means "inherit from whatever this ruleset extends"; an explicit
    # value overrides it. Using None rather than a default keeps a custom
    # ruleset from silently resetting the base's table borders to "keep".
    table_borders: TableBorders | None = None
    # Same inheritance rule as table_borders: None means "inherit", so a
    # custom ruleset does not silently reset the page setup.
    page: PageSetup | None = None

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

    table_borders = (
        overlay.table_borders
        if overlay.table_borders is not None
        else base.table_borders
    )
    page = overlay.page if overlay.page is not None else base.page
    return overlay.model_copy(
        update={
            "styles": styles,
            "extends": None,
            "table_borders": table_borders,
            "page": page,
        }
    )
