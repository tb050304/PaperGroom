"""Pydantic data models: the intermediate representation between layers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Role(str, Enum):
    """Semantic role assigned to a paragraph by the AI labeler.

    Stored as strings so YAML rulesets and JSON annotations read naturally.
    """

    DOCUMENT_TITLE = "document_title"
    TITLE_L1 = "title_l1"
    TITLE_L2 = "title_l2"
    TITLE_L3 = "title_l3"
    BODY = "body"
    FIGURE = "figure"
    FIGURE_CAPTION = "figure_caption"
    TABLE = "table"
    TABLE_CAPTION = "table_caption"
    REFERENCE = "reference"
    ABSTRACT = "abstract"
    FORMULA = "formula"
    LIST_ITEM = "list_item"
    QUOTE = "quote"
    COVER_INFO = "cover_info"
    UNKNOWN = "unknown"


class ParagraphStyle(BaseModel):
    """Concrete style for a paragraph and its runs.

    All fields optional; a field set to ``None`` means "do not change this
    property" — the original formatting is preserved. Unknown keys are
    rejected so a typo in a custom ruleset is an error rather than a silently
    ignored setting.
    """

    model_config = ConfigDict(extra="forbid")

    font_name: str | None = None
    font_name_east_asian: str | None = None
    font_size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    color_hex: str | None = None
    alignment: str | None = None  # left | center | right | justify
    line_spacing: float | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    first_line_indent_chars: float | None = None
    left_indent_pt: float | None = None

    @model_validator(mode="after")
    def _check_alignment(self) -> "ParagraphStyle":
        if self.alignment is not None:
            allowed = {"left", "center", "right", "justify"}
            if self.alignment not in allowed:
                raise ValueError(
                    f"alignment must be one of {allowed}, got {self.alignment!r}"
                )
        return self

    @model_validator(mode="after")
    def _check_color(self) -> "ParagraphStyle":
        if self.color_hex is not None:
            v = self.color_hex.lstrip("#")
            if len(v) != 6 or not all(c in "0123456789abcdefABCDEF" for c in v):
                raise ValueError(
                    f"color_hex must be a 6-digit hex (e.g. 'FF0000'), got {self.color_hex!r}"
                )
        return self

    @model_validator(mode="after")
    def _check_ranges(self) -> "ParagraphStyle":
        """Reject values that are almost certainly unit mistakes.

        The bounds are deliberately wide. They exist to catch a size written
        in twentieths of a point, or a percentage where a multiplier was
        meant — not to impose a house style. A negative first-line indent is
        legitimate: combined with a positive left indent it produces a
        hanging indent.
        """
        bounds = (
            ("font_size_pt", 4, 200),
            ("line_spacing", 0.5, 10),
            ("first_line_indent_chars", -10, 10),
            ("space_before_pt", 0, 500),
            ("space_after_pt", 0, 500),
            ("left_indent_pt", -200, 500),
        )
        for name, low, high in bounds:
            value = getattr(self, name)
            if value is not None and not (low <= value <= high):
                raise ValueError(
                    f"{name} must be between {low} and {high}, got {value}"
                )
        return self

    def is_empty(self) -> bool:
        """True if no style property is set (i.e. nothing to change)."""
        return all(v is None for v in self.model_dump().values())


class Paragraph(BaseModel):
    """A single paragraph as parsed from the docx, before/after labeling.

    Fields:
        index: ordinal position in the document (0-based, stable)
        text: concatenated run text (may be empty for image-only paragraphs)
        style_hint: the original ``w:pStyle`` value if any (e.g. "Heading1")
        has_image: True if the paragraph contains a ``w:drawing`` (inline image)
        has_table: True if this paragraph is actually a table (we treat a table
            as one block unit; the paragraph index still advances)
        has_formula: True if the paragraph contains an ``m:oMath`` element
        has_hyperlink: True if the paragraph contains a ``w:hyperlink``. Such
            paragraphs are never split (character offsets become ambiguous
            once text lives inside a nested element).
        original_pPr_xml: serialized ``<w:pPr>`` XML, kept so the writer can
            restore it if the ruleset asks to keep original paragraph properties
        source_index: the paragraph this one was split out of, or None when
            the paragraph was never split. Several paragraphs may share a
            source index.
        role_hint: deterministic role guess from text patterns alone
            (``structure.patterns.classify``). A prior for the labeler and a
            cross-check on its output — not a decision.
        role: assigned role (``UNKNOWN`` until the labeler runs)
        confidence: labeler confidence in ``role`` (0.0 if unlabeled)
        resolved_style: the style the AI decided to apply for this paragraph.
            Only the explicitly-set fields are applied; None fields keep the
            original formatting. If None, nothing is changed.
    """

    index: int
    text: str = ""
    style_hint: str | None = None
    has_image: bool = False
    has_table: bool = False
    has_formula: bool = False
    has_hyperlink: bool = False
    is_empty: bool = False
    original_pPr_xml: str | None = None
    source_index: int | None = None
    role_hint: Role | None = None
    role: Role = Role.UNKNOWN
    confidence: float = 0.0
    resolved_style: ParagraphStyle | None = None


class Document(BaseModel):
    """Parsed document: an ordered list of paragraphs plus the source path.

    The original python-docx ``Document`` object is intentionally NOT stored
    here (it's not pydantic-serializable and carries mutable state). The
    writer re-opens the source file from ``source_path`` to apply styles.

    ``splits`` records how the paragraphs below were derived from the source
    file, since after structure recovery ``paragraphs`` no longer maps
    one-to-one onto the docx. It maps a *source* paragraph index to the
    character ranges of the paragraphs it was split into; a source index
    absent from the mapping was not split. The writer replays these ranges
    on the XML so the two stay aligned.
    """

    source_path: str
    paragraphs: list[Paragraph] = Field(default_factory=list)
    splits: dict[int, list[tuple[int, int]]] = Field(default_factory=dict)


class LabelEntry(BaseModel):
    """One labeling result for a single paragraph.

    Deliberately carries no style: the labeler decides *what* a paragraph is,
    and the ruleset decides how it looks. Keeping the two apart is what makes
    the styling deterministic and testable.
    """

    index: int
    role: Role
    confidence: float


class Annotation(BaseModel):
    """Aggregated labeling result for a whole document."""

    entries: list[LabelEntry] = Field(default_factory=list)
