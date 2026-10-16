"""Prompt assembly for the role labeler.

The labeler does exactly one job: **decide what each paragraph is**. It never
decides a font size, a spacing value, or an indent — those come from the
ruleset and are applied deterministically downstream.

That split is the point. Asking a model to emit 12 numeric style fields per
paragraph after reading a long prose specification produced output that was
non-deterministic (the same role got different sizes in different
paragraphs), expensive (the whole specification was resent with every batch),
and impossible to unit-test. Asking it to pick one label from a fixed set is
something it is good at, and something we can measure.

The role guidance below is a deliberate compression of what used to be an
878-line prose document. Only the distinctions that actually change an answer
survive — everything structural (numbering, markers, section words) is
settled by pattern in ``papergroom.structure`` and never reaches the model.
"""

from __future__ import annotations

from ..models import Role
from ..rules.schema import Ruleset

# Marks a paragraph whose role was already settled by a pattern upstream. It
# is shown to the model for context (knowing a section boundary passed tells
# it what the following paragraphs are) but must not be re-labelled.
FIXED_MARK = "fixed"
# Marks a weak pattern guess, offered as a prior. The model may disagree.
HINT_MARK = "hint"

# One line per role, chosen to separate it from its nearest neighbour.
# Deliberately terse: a longer list would drift back toward the document this
# replaced, and the structural cases never get here anyway.
ROLE_GUIDE: dict[str, str] = {
    Role.DOCUMENT_TITLE.value: (
        "The title of the whole thesis. Exactly one per document, no numbering, "
        "appears first. NOT '摘要' and NOT '第1章 绪论'."
    ),
    Role.TITLE_L1.value: (
        "Chapter or major-section heading: numbered '第1章' / '1', or a structural "
        "word such as 摘要 / 参考文献 / 致谢."
    ),
    Role.TITLE_L2.value: "Sub-section heading, always numbered with two parts: '1.1 研究背景'.",
    Role.TITLE_L3.value: "Sub-sub-section heading, always numbered with three parts: '1.1.1 泛化问题'.",
    Role.BODY.value: (
        "Ordinary narrative prose. No numbering, no caption prefix, usually the "
        "longest paragraphs. The default role — most of a thesis is body."
    ),
    Role.ABSTRACT.value: (
        "A paragraph inside the abstract section, between the 摘要/Abstract heading "
        "and the 关键词/Keywords line."
    ),
    Role.FIGURE.value: "A paragraph whose content is an image.",
    Role.FIGURE_CAPTION.value: "The caption of a figure: '图1 系统架构图'. Sits next to the image.",
    Role.TABLE.value: "A paragraph whose content is a table.",
    Role.TABLE_CAPTION.value: "The caption of a table: '表2-1 实验结果'. Sits above the table.",
    Role.REFERENCE.value: (
        "One bibliography entry: starts with '[1]' or similar, and ends with the "
        "journal, year, or page numbers."
    ),
    Role.FORMULA.value: "A paragraph whose content is a displayed equation.",
    Role.LIST_ITEM.value: (
        "One item of a bulleted or numbered list inside the body. Several similar "
        "lines in a row. Distinguish from headings: list items are part of the "
        "narrative, headings introduce a new section."
    ),
    Role.QUOTE.value: "An indented block quoted from another source, often in 楷体.",
    Role.COVER_INFO.value: (
        "A cover-page layout row such as '姓名：张三'. Alignment is done with spaces. "
        "Never change these."
    ),
    Role.UNKNOWN.value: (
        "Use when the paragraph cannot be placed confidently, or is a table of "
        "contents entry, a header/footer, or a page number."
    ),
}

SYSTEM_PROMPT = """\
You classify paragraphs of a Chinese academic thesis by structural role.

You will receive paragraphs one per line as "<index>: <text>". A line may also
carry a marker before the index:

  context_only:true    — carried over from the previous batch purely as
                          context. Do NOT return a label for it.
  {fixed_mark}(<role>) — this paragraph's role is already settled. Do NOT
                          return a label for it.
  {hint_mark}(<role>)  — a weak guess from a text pattern. It is often right,
                          but you decide; disagree if the text says otherwise.

Your task: assign a role to every paragraph that carries no marker.

ROLES
{roles}

WHAT EACH ROLE WILL LOOK LIKE
This comes from the formatting ruleset and is applied after you decide. It is
context for you, not something you choose. A role's prominence is often the
strongest clue about what the paragraph is:

{styles}

RETURN STRICT JSON ONLY, in this shape:
{{"labels": [{{"index": 0, "role": "body", "confidence": 0.93}}]}}

- One entry per input line that carries no marker.
- "role" must be one of the role names above, spelled exactly.
- "confidence" is a float in [0,1]. Be honest: 0.9+ only when the evidence is
  clear, and use "unknown" rather than guessing at 0.5.
- Output JSON only — no prose, no markdown fences.\
"""


def style_summary(ruleset: Ruleset | None) -> str:
    """One line per role describing the formatting it will receive.

    Derived from the ruleset rather than written out by hand, so it cannot
    drift from what the applier actually does.
    """
    if ruleset is None:
        return "(no ruleset loaded)"

    lines: list[str] = []
    for role in Role:
        style = ruleset.styles.get(role.value)
        if style is None or style.is_empty():
            lines.append(f"  {role.value}: left as-is")
            continue
        bits: list[str] = []
        if style.font_name_east_asian:
            bits.append(style.font_name_east_asian)
        if style.font_size_pt is not None:
            bits.append(f"{style.font_size_pt:g}pt")
        if style.bold:
            bits.append("bold")
        if style.alignment:
            bits.append(style.alignment)
        lines.append(f"  {role.value}: {', '.join(bits) or 'left as-is'}")
    return "\n".join(lines)


def render_roles() -> str:
    return "\n".join(f"  {name}: {text}" for name, text in ROLE_GUIDE.items())


def build_messages(batch_text: str, ruleset: Ruleset | None) -> list[dict[str, str]]:
    """Assemble the message list for one labelling call."""
    system = SYSTEM_PROMPT.format(
        fixed_mark=FIXED_MARK,
        hint_mark=HINT_MARK,
        roles=render_roles(),
        styles=style_summary(ruleset),
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": batch_text},
    ]
