"""Sanity checks for a resolved ruleset.

Type and range errors are rejected by the schema while the file is parsed.
What is left are the problems that only show up once a ruleset has been
resolved and compared against the role taxonomy — a typo in a role name, or a
role the ruleset simply never mentions.
"""

from __future__ import annotations

from ..models import Role
from .schema import Ruleset


def validate_ruleset(ruleset: Ruleset) -> list[str]:
    """Return human-readable warnings. An empty list means nothing to flag.

    Warnings rather than errors: a partial ruleset is legitimate. Being
    silent about a role means "leave those paragraphs alone", which is a
    reasonable thing to want — it just should not happen by accident.
    """
    warnings: list[str] = []
    known = {role.value for role in Role}

    for role in sorted(ruleset.styles):
        if role not in known:
            warnings.append(
                f"unknown role {role!r} — no paragraph can ever have it, so this "
                f"style is dead. Known roles: {', '.join(sorted(known))}"
            )

    unstyled = sorted(known - set(ruleset.styles) - {Role.UNKNOWN.value})
    if unstyled:
        warnings.append(
            "no style for " + ", ".join(unstyled) + " — paragraphs with these "
            "roles keep their original formatting"
        )

    return warnings
