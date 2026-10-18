"""Paragraph role labeling with sliding-window batching.

The labeler answers one question per paragraph — *what is this?* — and
nothing else. It never decides formatting. Styles come from the ruleset, and
are resolved deterministically afterwards.

Three layers, in order of precedence:

1. **Patterns.** A paragraph that a text pattern settles beyond doubt — a
   bibliography entry, a bare section word, a short caption — never reaches
   the model at all. Free, instant, and reproducible.
2. **The model.** Everything else, batched by a sliding window so it can see
   enough context to tell a section heading from a list item. It returns a
   role and a confidence.
3. **Post-checks.** The pattern decisions are re-asserted after the model
   responds, so nothing it says can override them.

Why batching: a whole paper doesn't fit in one call, and one call per
paragraph is both expensive and context-poor — without siblings a model
cannot tell a level-1 from a level-2 heading. The window splits the
difference: greedy-pack paragraphs to a token budget, carry the tail of one
batch into the next as context, never split a paragraph.

Token estimation is deliberately crude (4 chars ≈ 1 token). Real
tokenisation would add a dependency and ~10x latency for ~5% better packing,
which is a bad trade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..config import LLMConfig, ProcessingConfig
from ..models import Annotation, Document, LabelEntry, Paragraph, Role
from ..rules.schema import Ruleset
from ..structure.patterns import certain_role, classify
from .cache import ResponseCache
from .client import LLMClient
from .prompts import CONTEXT_MARK, FIXED_MARK, build_messages

# Rough chars-per-token estimate. Under-estimating is safe (we pack less);
# over-estimating risks exceeding the context window. 4 is conservative for
# mixed CJK + Latin text (CJK is ~2 chars/token, Latin ~4-5).
_CHARS_PER_TOKEN = 4

# Trailing paragraphs carried into the next batch as context.
_CONTEXT_OVERLAP = 2

# Placeholder text for a paragraph whose content is an object.
_EMPTY_OBJECT_HINT = {
    "image": "[image]",
    "formula": "[formula]",
    "table": "[table]",
}

# Confidence assigned to a role a pattern decided. It is not a probability —
# the pattern is a rule, not an estimate — but it has to sort above the
# threshold that the model's answers are filtered by.
_PATTERN_CONFIDENCE = 1.0

# Confidence recorded when a hint has to stand in for a missing model answer.
# Below the model's acceptance threshold on purpose: it is a guess, not a
# judgement, and the number should not pretend otherwise.
_HINT_FALLBACK_CONFIDENCE = 0.5


@dataclass
class _Batch:
    """One call's worth of paragraphs.

    ``items`` are the paragraphs to show, in document order. Some of them may
    already have a decided role; they are rendered for context but excluded
    from the expected output. ``context`` holds paragraphs from the previous
    batch, carried over purely as evidence.
    """

    items: list[Paragraph] = field(default_factory=list)
    context: list[Paragraph] = field(default_factory=list)


def label_document(
    doc: Document,
    llm_config: LLMConfig,
    ruleset: Ruleset | None,
    processing: ProcessingConfig | None = None,
) -> Annotation:
    """Label every non-empty paragraph of ``doc`` in place; return the result.

    Mutates ``doc.paragraphs[i].role`` and ``.confidence``. Styles are *not*
    touched here — see :func:`papergroom.rules.resolve.resolve_styles`.
    """
    if processing is None:
        processing = ProcessingConfig()

    annotation = Annotation(entries=[])
    if not doc.paragraphs:
        return annotation

    labelable = [p for p in doc.paragraphs if not p.is_empty]

    # Fill in the pattern hint for anything that did not come through
    # structure recovery, so the model sees a hint whenever there is one.
    for para in labelable:
        if para.role_hint is None:
            para.role_hint = classify(para.text)

    # 1. Patterns decide what they can, without asking anyone.
    decided: dict[int, Role] = {}
    for para in labelable:
        role = certain_role(para.text)
        if role is not None:
            decided[para.index] = role
            para.role = role
            para.confidence = _PATTERN_CONFIDENCE

    # 2. Everything else goes to the model. The client is built lazily: a
    #    document the patterns fully account for needs no client at all.
    client: LLMClient | None = None
    for batch in _iter_batches(labelable, decided, processing.max_tokens_per_batch):
        batch_text, answerable = _render_batch(batch, decided)
        if not answerable:
            continue  # every paragraph here was already settled by a pattern

        if client is None:
            client = LLMClient(llm_config, _make_cache(processing))

        messages = build_messages(batch_text, ruleset)
        try:
            raw = client.complete(messages)
            parsed = _parse_labels(raw)
        except Exception as e:  # network or JSON failure
            # Leave the batch's roles as they are rather than crash the run,
            # so a partial result can still be written and inspected.
            import sys

            print(f"[papergroom] labeling batch failed: {e}", file=sys.stderr)
            parsed = []

        answered: set[int] = set()
        for display_index, role, confidence in parsed:
            para = answerable.get(display_index)
            if para is None:
                continue  # unknown index, or one the model was told to skip
            answered.add(para.index)
            if confidence >= processing.min_confidence:
                para.role = role
                para.confidence = confidence
            else:
                # Below the threshold we record the guess but act on nothing:
                # an unstyleable paragraph keeps its original formatting.
                para.role = Role.UNKNOWN
                para.confidence = confidence

        # A model that silently drops a line should not cost us the pattern
        # hint. This is not overriding a decision — there was no decision.
        for para in answerable.values():
            if para.index not in answered and para.role_hint is not None:
                para.role = para.role_hint
                para.confidence = _HINT_FALLBACK_CONFIDENCE

    # 3. Post-checks. Pattern decisions win, whatever the model said.
    for para in labelable:
        if para.index in decided:
            para.role = decided[para.index]
            para.confidence = _PATTERN_CONFIDENCE
        annotation.entries.append(
            LabelEntry(index=para.index, role=para.role, confidence=para.confidence)
        )

    return annotation


def _make_cache(processing: ProcessingConfig) -> ResponseCache | None:
    if not processing.cache_dir:
        return None
    return ResponseCache(processing.cache_dir)


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def _iter_batches(
    paragraphs: list[Paragraph], decided: dict[int, Role], max_tokens: int
) -> list[_Batch]:
    """Greedy-pack paragraphs into batches with a sliding overlap."""
    if not paragraphs:
        return []

    max_chars = max_tokens * _CHARS_PER_TOKEN
    batches: list[_Batch] = []

    i = 0
    context: list[Paragraph] = []
    while i < len(paragraphs):
        items: list[Paragraph] = []
        # Lengths are estimated with a placeholder display index; the real
        # index shifts by a character or two, which is immaterial against a
        # budget that is already a rough estimate.
        used = sum(len(_render_paragraph(p, decided, context=True)) for p in context)

        while i < len(paragraphs) and used < max_chars:
            line = _render_paragraph(paragraphs[i], decided, context=False)
            if used + len(line) > max_chars and items:
                break  # this paragraph would overflow a batch that has content
            items.append(paragraphs[i])
            used += len(line)
            i += 1

        batches.append(_Batch(items=items, context=list(context)))
        context = items[-_CONTEXT_OVERLAP:] if len(items) > _CONTEXT_OVERLAP else list(items)

    return batches


def _render_batch(
    batch: _Batch, decided: dict[int, Role]
) -> tuple[str, dict[int, Paragraph]]:
    """Render a batch for the model.

    Returns the text and a map from the index the model will quote back to
    the paragraph it refers to. Only paragraphs with no marker are in the
    map — those are the only ones the model is asked about.

    Indices are numbered per batch, monotonically, including the context and
    already-decided lines. Numbering only the answerable lines would make a
    fixed line and an answerable line claim the same number, and the model
    would be quoting an ambiguous index.
    """
    lines: list[str] = []
    answerable: dict[int, Paragraph] = {}
    index = 0

    for para in batch.context:
        lines.append(_render_paragraph(para, decided, context=True, display_index=index))
        index += 1

    for para in batch.items:
        fixed = para.index in decided
        lines.append(_render_paragraph(para, decided, context=False, display_index=index))
        if not fixed:
            answerable[index] = para
        index += 1

    return "\n".join(lines), answerable


def _render_paragraph(
    para: Paragraph,
    decided: dict[int, Role],
    *,
    context: bool,
    display_index: int = 0,
) -> str:
    """Render one paragraph as a single line.

    Format: ``<prefix><index>: <text>``. The prefix tells the model what is
    already known so it does not spend attention on it:

    * ``context_only:true`` — carried from the previous batch, do not label
    * ``fixed(<role>)``     — settled by a pattern, do not label
    * ``hint(<role>)``      — a weak pattern guess, may be overruled
    """
    text = para.text.strip()
    if not text:
        if para.has_image:
            text = _EMPTY_OBJECT_HINT["image"]
        elif para.has_formula:
            text = _EMPTY_OBJECT_HINT["formula"]
        elif para.has_table:
            text = _EMPTY_OBJECT_HINT["table"]

    if context:
        prefix = f"{CONTEXT_MARK} "
    elif para.index in decided:
        prefix = f"{FIXED_MARK}({decided[para.index].value}) "
    elif para.role_hint is not None:
        prefix = f"hint({para.role_hint.value}) "
    else:
        prefix = ""

    return f"{prefix}{display_index}: {text}"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_labels(raw: str) -> list[tuple[int, Role, float]]:
    """Parse the model's JSON into ``(index, role, confidence)`` triples.

    Tolerates the usual pollution — markdown fences, leading prose, an
    unknown role name — by dropping what it cannot use rather than failing.
    """
    text = raw.strip()
    if not text:
        return []

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []

    labels = data.get("labels") if isinstance(data, dict) else None
    if not isinstance(labels, list):
        return []

    out: list[tuple[int, Role, float]] = []
    for item in labels:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        role_name = item.get("role")
        if index is None or role_name is None:
            continue
        try:
            role = Role(role_name)
        except ValueError:
            continue
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            out.append((int(index), role, confidence))
        except (TypeError, ValueError):
            continue
    return out
