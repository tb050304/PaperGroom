"""Draft a ruleset from a natural-language description.

Custom rules are YAML precisely so that applying them is deterministic.
Writing that YAML by hand is a barrier, so the model drafts it — but only as
a *starting point*. The draft is schema-validated before it is written, and
the user is expected to review it. Nothing here changes how styles are
applied: once the file exists it is data, and the deterministic engine takes
over.

The prompt is explicit about the one failure mode that matters: inventing
values the user did not ask for. A draft that silently restates the base
ruleset is worse than no draft, because it looks like a decision.
"""

from __future__ import annotations

from ..config import LLMConfig
from ..models import Role
from ..rules.loader import load_ruleset, parse_ruleset_text
from ..rules.schema import Ruleset
from .client import LLMClient
from .prompts import style_summary

FIELD_REFERENCE = """\
font_name                 Latin font, e.g. "Times New Roman"
font_name_east_asian      Chinese font, e.g. 宋体 / 黑体 / 楷体
font_size_pt              point size (小四 = 12, 五号 = 10.5, 三号 = 16, 二号 = 22)
bold                      true / false
italic                    true / false
color_hex                 6 hex digits, e.g. "000000"
alignment                 left | center | right | justify
line_spacing              multiple of line height, e.g. 1.5
space_before_pt           points before the paragraph
space_after_pt            points after the paragraph
first_line_indent_chars   characters; 2 = two-character indent, negative = hanging
left_indent_pt            points"""

SYSTEM_PROMPT = """\
You turn a user's formatting requirements into a PaperGroom ruleset: a YAML
file that extends a built-in ruleset and overrides only what the user asked
for.

REQUIREMENTS
1. The file has exactly this shape, and no other top-level keys:

     name: <short slug, no spaces>
     extends: {base}
     styles:
       <role>:
         <property>: <value>

     table_borders:          # optional, only if the user mentions table borders
       style: three_line

   Allowed top-level keys are name, version, description, extends, styles and
   table_borders. Do not add a `roles` key or any other section.
2. Include ONLY the roles and properties the requirements actually mention.
   Everything you leave out is inherited from {base}; do not restate it.
3. Use these role names exactly:
{roles}
4. Style properties and their units:
{fields}
5. Omit a property entirely to mean "leave the document's own formatting
   alone". Never invent values the user did not ask for.
6. Convert Chinese type sizes: 初号42, 小初36, 一号26, 小一24, 二号22, 小二18,
   三号16, 小三15, 四号14, 小四12, 五号10.5, 小五9.
7. Table borders are a top-level key, not a role:
     table_borders:
       style: three_line      # keep | none | three_line
       outer_width_pt: 1.5
       header_width_pt: 0.75
8. Output strict YAML only. No prose, no markdown fences.

WHAT THE BASE RULESET CURRENTLY DOES (reference only; do not repeat it)
{styles}
"""


def strip_fences(text: str) -> str:
    """Remove a ```yaml fence if the model added one."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped.strip() + "\n"


def build_messages(
    description: str, base: Ruleset, base_name: str
) -> list[dict[str, str]]:
    system = SYSTEM_PROMPT.format(
        base=base_name,
        roles="\n".join(f"  {role.value}" for role in Role),
        fields=FIELD_REFERENCE,
        styles=style_summary(base),
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": description},
    ]


def draft_rules(
    description: str,
    llm_config: LLMConfig,
    base_name: str = "standard_thesis",
) -> str:
    """Ask the model for a ruleset draft. Returns YAML text, unvalidated."""
    base = load_ruleset(base_name)
    client = LLMClient(llm_config)
    raw = client.complete(
        build_messages(description, base, base_name), response_format=None
    )
    return strip_fences(raw)


def validate_draft(text: str) -> Ruleset:
    """Schema-check the draft. Raises ValueError if it is unusable."""
    return parse_ruleset_text(text)
