"""Rule engine: load YAML rulesets, validate, resolve styles, apply them."""

from .loader import list_rules, load_ruleset, parse_ruleset_text
from .resolve import resolve_styles
from .schema import ParagraphStyle, Ruleset, merge_rulesets, merge_styles
from .validate import validate_ruleset

__all__ = [
    "Ruleset",
    "ParagraphStyle",
    "load_ruleset",
    "list_rules",
    "parse_ruleset_text",
    "merge_rulesets",
    "merge_styles",
    "resolve_styles",
    "validate_ruleset",
]
