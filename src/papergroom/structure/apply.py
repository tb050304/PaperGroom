"""Apply a split plan to the docx XML tree.

The segmenter works in characters; this module turns those character ranges
into real ``<w:p>`` elements. Text is re-distributed at the run level, so
run formatting (font, bold, italic, colour) is preserved across the split —
a run that straddles a boundary is cloned and truncated on both sides.

Two safety properties matter more than completeness here:

* **Paragraphs carrying objects are never split.** A drawing, an equation,
  or a hyperlink makes character offsets ambiguous; the paragraph is left
  exactly as it was rather than risking a mangled image or broken link.
* **Source paragraphs are processed right to left.** In a python-docx
  document the paragraph list is positional, so splitting paragraph 3 first
  would shift every index after it. Going backwards means the indices of
  the paragraphs still to be processed never move. The earlier attempt at
  this code went forwards and produced operations for paragraphs that did
  not exist; the ordering here is what removes that whole class of bug.
"""

from __future__ import annotations

from copy import deepcopy

from docx import Document as DocxDocument
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"

# Character ranges per source paragraph index: ``{3: [(0, 6), (7, 106)]}``.
SplitPlan = dict[int, list[tuple[int, int]]]


def apply_splits(docx_doc: DocxDocument, plan: SplitPlan) -> None:
    """Rewrite ``docx_doc`` in place so its paragraphs match ``plan``."""
    if not plan:
        return

    body = docx_doc.element.body
    paragraphs = body.findall(f"{W}p")

    for source_index in sorted(plan, reverse=True):
        if source_index < 0 or source_index >= len(paragraphs):
            continue
        _split_paragraph(paragraphs[source_index], plan[source_index])


def _split_paragraph(p_el, segments: list[tuple[int, int]]) -> None:
    """Replace ``p_el`` with one paragraph per segment, dropping the gaps."""
    total = _text_length(p_el)
    kept = {tuple(seg) for seg in segments}

    bounds = sorted({b for seg in segments for b in seg} - {0, total})
    if not bounds:
        return

    if not _is_splittable(p_el, bounds):
        return

    # Split from the right: each boundary stays valid in the shrinking left
    # half, and the elements created end up in reverse order.
    created = []
    for pos in reversed(bounds):
        new_el = _split_at_char(p_el, pos)
        if new_el is None:  # pragma: no cover - guarded by _is_splittable
            return
        created.append(new_el)
    created.reverse()

    stops = [0, *bounds, total]
    ranges = [(stops[i], stops[i + 1]) for i in range(len(stops) - 1)]

    for el, rng in zip([p_el, *created], ranges):
        if rng not in kept:
            el.getparent().remove(el)


def _is_splittable(p_el, bounds: list[int]) -> bool:
    """True when every boundary can be cut without touching an object.

    Checked up front so a failure cannot leave the paragraph half-split.
    """
    if p_el.find(f".//{W}drawing") is not None:
        return False
    if p_el.find(f".//{W}hyperlink") is not None:
        return False
    for elem in p_el.iter():
        if etree.QName(elem).localname == "oMath":
            return False

    runs = _run_spans(p_el)
    return all(_span_at(runs, b) is not None for b in bounds)


def _text_length(p_el) -> int:
    return sum(len(t.text) for t in p_el.findall(f"{W}r/{W}t") if t.text)


class _RunSpan:
    __slots__ = ("element", "start", "end")

    def __init__(self, element, start: int, end: int):
        self.element = element
        self.start = start
        self.end = end


def _run_spans(p_el) -> list[_RunSpan]:
    """Character span of each direct ``<w:r>`` that holds text."""
    spans: list[_RunSpan] = []
    offset = 0
    for run in p_el.findall(f"{W}r"):
        t = run.find(f"{W}t")
        if t is None or not t.text:
            continue
        spans.append(_RunSpan(run, offset, offset + len(t.text)))
        offset += len(t.text)
    return spans


def _span_at(spans: list[_RunSpan], position: int) -> tuple[_RunSpan, int] | None:
    for span in spans:
        if span.start <= position < span.end:
            return span, position - span.start
    return None


def _split_at_char(p_el, position: int):
    """Cut ``p_el`` at ``position``; return the right half as a new ``<w:p>``.

    The left half stays in ``p_el``.
    """
    hit = _span_at(_run_spans(p_el), position)
    if hit is None:
        return None
    span, offset = hit

    run_el = span.element
    t_el = run_el.find(f"{W}t")
    if t_el is None or t_el.text is None:
        return None

    left, right = t_el.text[:offset], t_el.text[offset:]
    t_el.text = left
    _preserve_space(t_el, left)

    right_run = deepcopy(run_el)
    right_t = right_run.find(f"{W}t")
    if right_t is not None:
        right_t.text = right
        _preserve_space(right_t, right)

    new_p = etree.Element(f"{W}p")
    pPr = p_el.find(f"{W}pPr")
    if pPr is not None:
        new_p.append(deepcopy(pPr))
    new_p.append(right_run)

    children = list(p_el)
    for child in children[children.index(run_el) + 1 :]:
        p_el.remove(child)
        new_p.append(child)

    p_el.addnext(new_p)
    return new_p


def _preserve_space(t_el, text: str) -> None:
    """Keep leading/trailing spaces from being collapsed by Word."""
    if text != text.strip():
        t_el.set(f"{{{XML_NS}}}space", "preserve")
    elif f"{{{XML_NS}}}space" in t_el.attrib:
        del t_el.attrib[f"{{{XML_NS}}}space"]
