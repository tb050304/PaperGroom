"""Detect paragraphs where a numbered heading is concatenated with body text.

Handles patterns like:
- "1 研究背景当前高校..." — L1 heading + body
- "1.1 研究方法我们采用..." — L2 heading + body
- "1.2.3 详细设计该模块..." — L3 heading + body
- "第1章 绪论本文研究..." — chapter heading + body
- "一、引言随着..." — Chinese ordinal heading + body

The split position is found by:
1. Match the heading numbering prefix at the start.
2. Within a reasonable title length (2-40 chars after prefix), find a strong
   body-start word (two+ characters, like "本文", "随着", "基于", etc.).

We use two-character (or longer) body-start words because single characters
are too ambiguous (e.g. "研" appears in both "研究背景" (heading) and
"研究表明" (body start)).
"""

from __future__ import annotations

import re

from ..models import Document
from .models import SplitOperation

# Strong multi-character words that start a body paragraph.
# These almost never appear inside a heading title.
_BODY_START_WORDS = [
    "本文", "本研究", "本章", "本论文", "本课题", "本次",
    "我们", "笔者",
    "随着", "基于", "通过", "针对", "对于", "根据", "按照", "由于",
    "为了", "为实现", "为解决", "为验证",
    "该方法", "该系统", "该模型", "该算法", "该技术",
    "这种", "这样", "因此", "所以", "然而", "但是", "此外", "另外",
    "首先", "其次", "最后", "然后",
    "例如", "比如", "具体来说",
    "当前", "目前", "传统上",
    "实验结果", "研究表明", "分析发现", "结果显示",
    "学生", "教师", "高校",
]

# Heading numbering prefix patterns.
# Each regex matches JUST the numbering part at the start of the string.
_HEADING_PREFIXES = [
    # "第N章 / 第N节 / 第N篇"
    re.compile(r"^第[一二三四五六七八九十百千\d]+[章节节篇]\s*"),
    # "1.1.1 " / "1.1 " / "12 " (number + space)
    re.compile(r"^\d+(?:\.\d+){0,2}\s+"),
    # "一、" / "二、"
    re.compile(r"^[一二三四五六七八九十]+、\s*"),
    # "（一）" / "（二）"
    re.compile(r"^（[一二三四五六七八九十]+）\s*"),
]

# Min/max title length (chars after the numbering prefix).
_MIN_TITLE_LEN = 2
_MAX_TITLE_LEN = 40


def detect_merged_headings(doc: Document) -> list[SplitOperation]:
    """Detect heading+body concatenations.

    Operates on original paragraph indices.
    """
    ops: list[SplitOperation] = []

    for p in doc.paragraphs:
        if p.is_empty or p.has_image or p.has_formula or p.has_table:
            continue

        text = p.text
        if not text or len(text) < 10:
            continue

        split_pos = _find_split_position(text)
        if split_pos is not None:
            ops.append(
                SplitOperation(
                    paragraph_index=p.index,
                    split_positions=[split_pos],
                    reason="merged_heading",
                )
            )

    return ops


def _find_split_position(text: str) -> int | None:
    """Find the character position where a heading ends and body begins.

    Returns None if no clear heading+body boundary is found.
    """
    prefix_end = _find_prefix_end(text)
    if prefix_end is None:
        return None

    search_start = prefix_end + _MIN_TITLE_LEN
    search_end = min(prefix_end + _MAX_TITLE_LEN, len(text))

    if search_start >= search_end:
        return None

    region = text[search_start:search_end]

    # Find the earliest body-start word.
    earliest: int | None = None
    for word in _BODY_START_WORDS:
        idx = region.find(word)
        if idx != -1:
            abs_pos = search_start + idx
            if earliest is None or abs_pos < earliest:
                earliest = abs_pos

    return earliest


def _find_prefix_end(text: str) -> int | None:
    """End position of the heading numbering prefix at start of text."""
    for pattern in _HEADING_PREFIXES:
        m = pattern.match(text)
        if m:
            return m.end()
    return None
