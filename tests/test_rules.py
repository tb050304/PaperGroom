"""Tests for ruleset layering — the "your rules win" requirement.

A custom ruleset extends the built-in one and overrides only what it cares
about. Merge granularity is role → field, so setting one property of one role
changes exactly that property and inherits everything else.

This is the whole reason the ruleset is data rather than code: a school
template should be a short file, not a fork.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from papergroom.models import ParagraphStyle
from papergroom.rules.loader import load_ruleset
from papergroom.rules.schema import Ruleset, merge_rulesets, merge_styles
from papergroom.rules.validate import validate_ruleset


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Field-by-field merge
# ---------------------------------------------------------------------------


def test_overlay_wins_field_by_field():
    base = ParagraphStyle(font_size_pt=12, alignment="justify", bold=False)
    overlay = ParagraphStyle(font_size_pt=14)

    merged = merge_styles(base, overlay)

    assert merged.font_size_pt == 14
    assert merged.alignment == "justify"  # inherited
    assert merged.bold is False  # inherited, and False is a real value


def test_overlay_without_base_is_just_the_overlay():
    overlay = ParagraphStyle(font_size_pt=14)
    assert merge_styles(None, overlay) == overlay


def test_booleans_can_be_turned_off():
    assert merge_styles(ParagraphStyle(bold=True), ParagraphStyle(bold=False)).bold is False


def test_base_roles_survive_and_overlay_roles_are_added():
    base = Ruleset(name="base", styles={"body": ParagraphStyle(font_size_pt=12)})
    overlay = Ruleset(name="user", styles={"title_l1": ParagraphStyle(font_size_pt=16)})

    merged = merge_rulesets(base, overlay)

    assert merged.name == "user"
    assert merged.styles["body"].font_size_pt == 12
    assert merged.styles["title_l1"].font_size_pt == 16
    assert merged.extends is None


# ---------------------------------------------------------------------------
# Loader: resolving extends
# ---------------------------------------------------------------------------


def test_extends_a_builtin(tmp_path: Path):
    path = _write(
        tmp_path / "school.yaml",
        """
name: school
extends: standard_thesis
styles:
  body:
    font_size_pt: 14
""",
    )

    ruleset = load_ruleset(str(path))
    body = ruleset.style_for("body")

    assert body.font_size_pt == 14  # overridden
    assert body.font_name_east_asian == "宋体"  # inherited
    assert body.alignment == "justify"  # inherited
    assert body.first_line_indent_chars == 2  # inherited
    # Roles the overlay says nothing about are still complete.
    assert ruleset.style_for("title_l1").font_size_pt == 16


def test_extends_a_relative_path(tmp_path: Path):
    _write(
        tmp_path / "base.yaml",
        """
name: base
styles:
  body:
    font_size_pt: 12
    alignment: justify
""",
    )
    path = _write(
        tmp_path / "user.yaml",
        """
name: user
extends: ./base.yaml
styles:
  body:
    font_size_pt: 15
""",
    )

    body = load_ruleset(str(path)).style_for("body")

    assert body.font_size_pt == 15
    assert body.alignment == "justify"


def test_extends_chain_of_three(tmp_path: Path):
    _write(tmp_path / "a.yaml", "name: a\nstyles:\n  body:\n    font_size_pt: 10\n    bold: true\n")
    _write(tmp_path / "b.yaml", "name: b\nextends: ./a.yaml\nstyles:\n  body:\n    font_size_pt: 11\n")
    path = _write(tmp_path / "c.yaml", "name: c\nextends: ./b.yaml\nstyles:\n  body:\n    italic: true\n")

    body = load_ruleset(str(path)).style_for("body")

    assert body.font_size_pt == 11  # from b, which overrode a
    assert body.bold is True  # from a, untouched by b and c
    assert body.italic is True  # from c


def test_extends_cycle_is_rejected(tmp_path: Path):
    _write(tmp_path / "a.yaml", "name: a\nextends: ./b.yaml\nstyles: {}\n")
    _write(tmp_path / "b.yaml", "name: b\nextends: ./a.yaml\nstyles: {}\n")

    with pytest.raises(ValueError, match="cycle"):
        load_ruleset(str(tmp_path / "a.yaml"))


def test_missing_ruleset_raises():
    with pytest.raises(FileNotFoundError):
        load_ruleset("no_such_ruleset")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("font_size_pt", 1200),  # twips where points were meant
        ("line_spacing", 150),  # percent where a multiplier was meant
        ("first_line_indent_chars", -50),
        ("space_before_pt", -1),
    ],
)
def test_absurd_values_are_rejected(field: str, value: float):
    with pytest.raises(ValueError):
        ParagraphStyle(**{field: value})


def test_negative_first_line_indent_is_allowed():
    """It is what makes a hanging indent possible."""
    style = ParagraphStyle(first_line_indent_chars=-2.0)
    assert style.first_line_indent_chars == -2.0


def test_a_misspelled_field_is_rejected_not_ignored():
    with pytest.raises(ValueError):
        ParagraphStyle(font_size=12)  # meant font_size_pt


def test_a_misspelled_ruleset_key_is_rejected():
    with pytest.raises(ValueError):
        Ruleset(name="t", style={"body": {}})  # meant styles


def test_builtin_ruleset_has_no_warnings():
    assert validate_ruleset(load_ruleset("standard_thesis")) == []


def test_unknown_role_is_flagged():
    warnings = validate_ruleset(Ruleset(name="t", styles={"title_l9": ParagraphStyle()}))
    assert any("unknown role" in w for w in warnings)


def test_missing_roles_are_reported():
    warnings = validate_ruleset(Ruleset(name="t", styles={"body": ParagraphStyle()}))
    assert any("no style for" in w and "title_l1" in w for w in warnings)


def test_reference_style_has_a_hanging_indent():
    """The built-in ruleset should outdent '[1]' and indent wrapped lines."""
    ref = load_ruleset("standard_thesis").style_for("reference")
    assert ref.left_indent_pt == 21
    assert ref.first_line_indent_chars == -2.0
    # 10.5pt × -2 = -21pt, exactly cancelling the left indent on line one.
    assert ref.font_size_pt * ref.first_line_indent_chars == -ref.left_indent_pt
