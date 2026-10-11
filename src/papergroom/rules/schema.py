"""Pydantic schema for a formatting ruleset (YAML).

NOTE: In the new architecture, the YAML ruleset is NOT the primary source
of formatting decisions. The AI labeler reads the formatting rules (either
the built-in default thesis rules or a user-provided rules text) and outputs
a ``ParagraphStyle`` per paragraph directly. The YAML ruleset is kept as
an optional fallback / preset mechanism, but ``defaults`` no longer force-
inherits into every role — each role's style is applied as-is.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import ParagraphStyle


class Ruleset(BaseModel):
    """A loaded ruleset: defaults + per-role style overrides.

    ``defaults`` is kept for backward compatibility but is NOT force-merged
    into role styles. Use :meth:`style_for` to get a role's style; if the
    role has no explicit style, an empty :class:`ParagraphStyle` is
    returned (meaning "change nothing").
    """

    name: str
    version: int = 1
    description: str | None = None
    defaults: ParagraphStyle = Field(default_factory=ParagraphStyle)
    styles: dict[str, ParagraphStyle] = Field(default_factory=dict)

    def style_for(self, role_name: str) -> ParagraphStyle:
        """Return the style for a role.

        Unlike the old behavior, defaults are NOT merged in. If the role
        has no explicit style entry, an empty ParagraphStyle is returned
        (which the applier treats as "change nothing").
        """
        role_style = self.styles.get(role_name)
        if role_style is None:
            return ParagraphStyle()
        return role_style.model_copy()
