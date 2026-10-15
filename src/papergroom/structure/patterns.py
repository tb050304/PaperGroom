"""Deterministic text patterns for recovering structure from flat text.

Everything here is pure regex work on plain strings: no docx, no LLM. That
makes the rules fast, trivially testable, and — unlike an LLM — exactly
reproducible.

The patterns target the damage that AI-generated / copy-pasted documents
actually show. Measured on a real one, the three dominant modes are:

1. A heading and its body merged into a single paragraph::

       "1 研究背景 当前高校课程论文、毕业设计均有严格统一的格式规范……"

2. Several bibliography entries merged into a single paragraph::

       "[1] 李华。……[J]. 计算机工程与应用，2024,60 (06):99-104. [2] 张强。……"

3. A section word glued to its content with a colon::

       "摘要：随着信息化教育快速发展……"

Design notes
------------
The rules are deliberately conservative. A wrong split is worse than a
missed one: it destroys text that was fine and makes the output
unpredictable. Where the text is genuinely ambiguous (a heading with no
separator before its body), we do *not* guess — the paragraph is left
intact and an AI fallback can consider it later.
"""

from __future__ import annotations

import re

from ..models import Role

# Whitespace that may separate a heading from its body. `\s` in Python's
# str patterns already covers U+3000, so `[^\s]` below excludes it too.
_SEP = r"[ \t　]"

# ---------------------------------------------------------------------------
# Heading numbering
# ---------------------------------------------------------------------------

_CJK_NUM = "一二三四五六七八九十百零〇"

# "第1章" / "第三章" / "第3节"
_CHAPTER = rf"第[{_CJK_NUM}\d]{{1,3}}[章节節篇]"

# "1" / "1.1" / "1.1.1". Each component is capped at two digits so that a
# year ("2024") can never be mistaken for heading numbering.
_DOTTED = r"\d{1,2}(?:\.\d{1,2})*"

# Full numbering token, anchored at the start of a paragraph.
HEADING_NUMBERING = rf"(?:{_CHAPTER}|{_DOTTED})"

# A heading whose body is glued on with whitespace:
#
#     "1 研究背景 当前高校课程论文、毕业设计……"
#      ^num      ^title ^--------- body (>= 10 chars)
#
# `title` stops at the next whitespace and may not start with a digit, which
# is what keeps "2024 年研究表明……" from matching as a heading.
MERGED_HEADING_RE = re.compile(
    rf"^(?P<num>{HEADING_NUMBERING}){_SEP}+"
    rf"(?P<title>[^\s\d][^\s]{{0,29}})"
    rf"{_SEP}+"
    rf"(?P<body>\S.{{9,}})$"
)

# A heading standing on its own, no body attached:
# "1 研究背景", "1.1 传统排版存在的问题".
HEADING_ONLY_RE = re.compile(
    rf"^(?P<num>{HEADING_NUMBERING}){_SEP}+(?P<title>\S.*)$"
)

# ---------------------------------------------------------------------------
# Section words
# ---------------------------------------------------------------------------

# Words that act as an unnumbered level-1 heading. Only these may be split on
# a colon — a blanket `^X：` rule would also fire on cover-page rows like
# "作者：王同学" and destroy the cover layout.
#
# 关键词 / Keywords are deliberately absent: the keyword line is one unit
# ("关键词：A；B；C") and splitting the label off it is wrong.
SPLIT_SECTION_WORDS: tuple[str, ...] = (
    "摘要",
    "Abstract",
    "ABSTRACT",
    "参考文献",
    "References",
    "REFERENCES",
    "目录",
    "致谢",
    "Acknowledgements",
    "Acknowledgments",
    "结论",
    "绪论",
    "引言",
    "前言",
    "附录",
    "Appendix",
)

_SECTION_ALT = "|".join(
    re.escape(w) for w in sorted(SPLIT_SECTION_WORDS, key=len, reverse=True)
)

# "摘要：随着……"  ->  heading "摘要" + body "随着……"
# The trailing lookahead means "参考文献：" with nothing after it does not
# match, so a bare section heading is left alone.
SECTION_COLON_RE = re.compile(rf"^(?P<head>{_SECTION_ALT})\s*[：:]\s*(?=\S)")

# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

REF_MARKER_RE = re.compile(r"\[\d{1,3}\]")

# A bibliography entry ends in "." or "。" and the next marker starts right
# after it: "...99-104. [2] 张强。...". Requiring that terminator is what
# stops an inline citation pair — "研究表明 [1] 与 [2] 存在差异" — from being
# torn apart.
REF_BOUNDARY_BEFORE = re.compile(r"[.。]\s*$")

# ---------------------------------------------------------------------------
# Captions (role hints only; captions are not split)
# ---------------------------------------------------------------------------

FIGURE_CAPTION_RE = re.compile(r"^图\s*\d")
TABLE_CAPTION_RE = re.compile(r"^表\s*\d")


def heading_level(numbering: str) -> int:
    """Map a numbering token to a heading level.

    ``第3章`` -> 1, ``1`` -> 1, ``1.1`` -> 2, ``1.1.1`` -> 3.
    """
    if numbering.startswith("第"):
        return 1
    return numbering.count(".") + 1


def classify(text: str) -> Role | None:
    """Best-effort role for a segment, from its text alone.

    Returns ``None`` when the text gives no reliable signal. These are hints,
    not verdicts: the AI labeler decides roles, and these serve as a
    deterministic cross-check on its output.

    The trailing-punctuation guard matters — a body paragraph that merely
    starts with a number ("1 首先，本文……") reads as prose and must not be
    claimed as a heading.
    """
    t = text.strip()
    if not t:
        return None

    # "参考文献：" / "摘要" — a bare section word, optionally with a colon.
    for word in SPLIT_SECTION_WORDS:
        if t == word or t in (f"{word}：", f"{word}:"):
            return Role.TITLE_L1

    if REF_MARKER_RE.match(t):
        return Role.REFERENCE

    m = HEADING_ONLY_RE.match(t)
    if m and not t.endswith(("。", "！", "？", ".", "；", ";")):
        return Role(f"title_l{heading_level(m.group('num'))}")

    if FIGURE_CAPTION_RE.match(t):
        return Role.FIGURE_CAPTION
    if TABLE_CAPTION_RE.match(t):
        return Role.TABLE_CAPTION

    return None
