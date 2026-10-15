"""Split one paragraph's text into semantic segments.

This module is pure: it takes a string and returns character ranges. It
never touches a docx and never calls a model, which means the riskiest part
of structure recovery can be tested and scored on plain text fixtures
(see ``tests/fixtures/segment_cases.yaml`` and ``scripts/eval_segmenter.py``).

Segments are expressed as ``[start, end)`` offsets into the *original*
paragraph text. Anything not covered by a segment is dropped — that is how
the separator in "摘要：随着……" disappears: the heading segment ends before
the colon and the body segment starts after it, so the colon falls in a gap.

Rules are applied recursively. A chapter heading whose body happens to
contain the whole bibliography, for instance, splits twice: once at the
heading boundary, then again between the reference entries.

Known limitations
-----------------
* A heading containing an internal space ("1 研究 背景 当前……") is split at
  the first space, not the last. There is no deterministic signal that
  distinguishes it from the normal "1 研究背景 当前……", so it is left to the
  AI fallback rather than guessed at here.
* Chinese ordinal headings ("一、引言") are not recognized. Supporting them
  safely needs a rule set validated against real documents; guessing now
  would risk splitting genuine list items.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Role
from . import patterns

# Bound on recursive re-splitting. Each level must make the text strictly
# shorter, so this is only a backstop against a pathological rule.
_MAX_DEPTH = 4

# Shortest text that may count as a bibliography entry before a split point.
# Real entries are far longer; the floor exists only to reject debris.
_MIN_ENTRY_CHARS = 5


@dataclass(frozen=True)
class Segment:
    """One semantic unit recovered from a paragraph.

    ``start`` and ``end`` are offsets into the source paragraph's text, so
    the docx layer can reproduce the same split on the XML.
    """

    text: str
    start: int
    end: int
    role_hint: Role | None = None


def segment_text(text: str) -> list[Segment]:
    """Split ``text`` into semantic segments, in document order.

    Returns a single segment covering (most of) the input when nothing
    recognizable is found — callers should treat a one-element result as
    "no split".
    """
    segments: list[Segment] = []
    for start, end in _segment_ranges(text, 0, 0):
        piece = text[start:end]
        segments.append(
            Segment(
                text=piece,
                start=start,
                end=end,
                role_hint=patterns.classify(piece),
            )
        )
    return segments


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _segment_ranges(text: str, base: int, depth: int) -> list[tuple[int, int]]:
    """Absolute ``[start, end)`` ranges, recursively subdivided.

    ``base`` is where ``text`` begins in the original paragraph, so offsets
    stay absolute across recursion.
    """
    if depth >= _MAX_DEPTH or not text.strip():
        return _trim_all(text, base, [(0, len(text))])

    pieces = _split_once(text)
    if pieces is None:
        return _trim_all(text, base, [(0, len(text))])

    out: list[tuple[int, int]] = []
    for start, end in pieces:
        if end <= start:
            continue
        out.extend(_segment_ranges(text[start:end], base + start, depth + 1))

    # A rule that produced nothing usable must not erase the paragraph.
    return out or [(base, base + len(text))]


def _split_once(text: str) -> list[tuple[int, int]] | None:
    """Apply the first matching rule; ``None`` when no rule applies.

    Order is significant: a section word is checked before the merged-heading
    rule so that "参考文献：……" is not read as an unnumbered heading with an
    unparseable body.
    """
    for rule in (_split_section_colon, _split_merged_heading, _split_references):
        pieces = rule(text)
        if pieces is not None:
            return pieces
    return None


def _split_section_colon(text: str) -> list[tuple[int, int]] | None:
    """"摘要：随着……" -> "摘要" + "随着……" (colon dropped)."""
    m = patterns.SECTION_COLON_RE.match(text)
    if not m:
        return None
    return [(0, m.end("head")), (m.end(), len(text))]


def _split_merged_heading(text: str) -> list[tuple[int, int]] | None:
    """"1 研究背景 当前高校……" -> "1 研究背景" + "当前高校……"."""
    m = patterns.MERGED_HEADING_RE.match(text)
    if not m:
        return None

    title, body = m.group("title"), m.group("body")

    # The title is taken to be the first whitespace-delimited run, which is
    # right for Chinese but wrong for a multi-word Latin heading:
    #
    #     "1.1 Background and Motivation We study ..."
    #              ^ title as parsed    ^ actually part of the title
    #
    # A Latin title followed by a lower-case word means the boundary is
    # mid-phrase, so we back off. "1 Introduction This paper ..." is
    # unaffected — the body starts upper-case, as a real body would.
    if title[-1:].isascii() and title[-1:].isalpha() and body[0].isascii():
        if body[0].islower():
            return None

    return [(0, m.end("title")), (m.start("body"), len(text))]


def _split_references(text: str) -> list[tuple[int, int]] | None:
    """"[1] …[J]. …104. [2] …" -> one segment per entry.

    Requires at least two markers, and each marker after the first must follow
    the end of a sentence. That guard is what keeps an inline citation pair
    ("研究表明 [1] 与 [2] 存在差异") intact.
    """
    markers = list(patterns.REF_MARKER_RE.finditer(text))
    if len(markers) < 2:
        return None

    # Each accepted boundary must be preceded by a substantive entry. The
    # length floor keeps a stray terminator from being carved off as its own
    # paragraph: in "。[1] 甲。 [2] 乙。" the text before "[2]" starts with the
    # orphan "。", which is not an entry.
    starts: list[int] = []
    previous = 0
    for marker in markers:
        position = marker.start()
        if position == 0:  # the first entry is not a split point
            continue
        if not patterns.REF_BOUNDARY_BEFORE.search(text[:position]):
            continue
        if len(text[previous:position].strip()) < _MIN_ENTRY_CHARS:
            continue
        starts.append(position)
        previous = position

    if not starts:
        return None

    bounds = [0, *starts, len(text)]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def _trim_all(
    text: str, base: int, pieces: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Trim surrounding whitespace from each piece, dropping empties.

    The trimmed whitespace becomes a gap, so it is removed from the output
    rather than carried into a segment. That is what strips the trailing
    space from "…99-104. [2] …" (segment 1) and the separator in
    "1 研究背景 当前…" (which the heading rule already excluded).
    """
    out: list[tuple[int, int]] = []
    for start, end in pieces:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            out.append((base + start, base + end))
    return out or [(base, base + len(text))]
