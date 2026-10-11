"""Paragraph role labeler with sliding-window batching.

Strategy
--------
A whole paper (thousands of paragraphs) doesn't fit in one LLM call, and
per-paragraph calls are both expensive and context-poor (the model can't
tell an H1 from an H2 without seeing siblings). The sliding-window
batcher splits the difference:

1. Greedy pack paragraphs into a batch until the estimated token count
   hits ``max_tokens_per_batch``. A paragraph is never split across
   batches.
2. Carry the last 1-2 paragraphs of the previous batch as *context only*
   into the next batch, marked ``context_only:true``. The model sees them
   (so it can use surrounding text as evidence) but is told not to label
   them. This avoids re-labeling the same paragraph twice and keeps
   batch boundaries from cutting semantics in half.
3. For each batch, call the LLM with JSON-mode response, parse, and
   merge into the document's :class:`Paragraph` entries.
4. Confidence below ``min_confidence`` leaves the paragraph's role as
   ``UNKNOWN`` so the applier skips it (the original style is preserved).

Token estimation is intentionally crude (4 chars ≈ 1 token). It doesn't
need to be exact — we just need to stay under the model's context limit
with margin. Real tokenization would add a dependency and ~10x latency
for ~5% better packing, which is a bad trade for an MVP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import LLMConfig, ProcessingConfig
from ..models import Annotation, Document, LabelEntry, Paragraph, ParagraphStyle, Role
from .client import LLMClient
from .prompts import build_messages

# Rough chars-per-token estimate. Under-estimating is safe (we pack less),
# over-estimating risks exceeding context. 4 is a conservative value for
# mixed CJK + Latin text (CJK is ~2 chars/token, Latin ~4-5).
_CHARS_PER_TOKEN = 4

# Number of trailing paragraphs to carry into the next batch as context.
_CONTEXT_OVERLAP = 2

# Marker prefix for paragraphs that should be used as context, not labeled.
_CONTEXT_PREFIX = "context_only:true"

# Marker for paragraphs whose text is empty but contain an object.
_EMPTY_OBJECT_HINT = {
    "image": "[image]",
    "table": "[table]",
    "formula": "[formula]",
}


@dataclass
class _Batch:
    """One LLM call's worth of paragraphs.

    ``entries`` are the paragraphs to label. ``context`` are trailing
    paragraphs from the previous batch, carried over as evidence but
    excluded from the output.
    """

    entries: list[Paragraph]
    context: list[Paragraph] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.context is None:
            self.context = []


def label_document(
    doc: Document,
    llm_config: LLMConfig,
    rules_text: str,
    processing: ProcessingConfig | None = None,
) -> Annotation:
    """Label every paragraph in ``doc`` in place; return the annotation.

    The AI both identifies each paragraph's role AND decides the style
    properties to apply, based on ``rules_text``. The resolved style is
    stored on ``para.resolved_style``.

    Args:
        doc: Parsed document. ``doc.paragraphs[i].role`` and
            ``resolved_style`` are mutated.
        llm_config: LLM configuration (provider, key, model).
        rules_text: The formatting rules (natural language / markdown)
            that the AI should follow when deciding styles.
        processing: Optional processing overrides; defaults read from env.

    Returns:
        An :class:`Annotation` with one entry per labeled paragraph.
        Paragraphs left as UNKNOWN (low confidence) are included.
    """
    if processing is None:
        processing = ProcessingConfig()

    if not doc.paragraphs:
        return Annotation(entries=[])

    client = LLMClient(llm_config)
    annotation = Annotation(entries=[])

    # Skip empty paragraphs: they carry no text or object for the AI to
    # reason about, and sending them just burns tokens + adds noise. They
    # stay role=UNKNOWN and the applier leaves them untouched.
    labelable = [p for p in doc.paragraphs if not p.is_empty]

    for batch in _iter_batches(labelable, processing.max_tokens_per_batch):
        batch_text = _render_batch(batch)
        messages = build_messages(batch_text, rules_text)
        try:
            raw = client.complete(messages)
            entries = _parse_labels(raw)
        except Exception as e:
            # Network / parse failure → leave the whole batch unknown.
            # We surface the error via stderr rather than crash the run,
            # so partial results can still be written.
            import sys

            print(f"[papergroom] labeling batch failed: {e}", file=sys.stderr)
            entries = []

        # Map entries back to paragraphs. Indices in the response are
        # relative to the *labeled* paragraphs in the batch (context_only
        # excluded), in the same order as rendered.
        labeled = batch.entries
        for entry in entries:
            if 0 <= entry.index < len(labeled):
                para = labeled[entry.index]
                if entry.confidence >= processing.min_confidence:
                    para.role = entry.role
                    para.confidence = entry.confidence
                    para.resolved_style = entry.style
                else:
                    para.role = Role.UNKNOWN
                    para.confidence = entry.confidence
                    para.resolved_style = None
                annotation.entries.append(
                    LabelEntry(
                        index=para.index,
                        role=para.role,
                        confidence=para.confidence,
                        style=para.resolved_style,
                    )
                )

    return annotation


def _iter_batches(
    paragraphs: list[Paragraph], max_tokens: int
) -> list[_Batch]:
    """Greedy-pack paragraphs into batches with sliding overlap.

    Returns a list (not a generator) so callers can inspect the plan and
    tests can assert on it without consuming.
    """
    if not paragraphs:
        return []

    max_chars = max_tokens * _CHARS_PER_TOKEN
    batches: list[_Batch] = []

    i = 0
    context: list[Paragraph] = []
    while i < len(paragraphs):
        current: list[Paragraph] = []
        # Reserve room for context rendering.
        used = sum(len(_render_paragraph(p, context=True)) for p in context)

        while i < len(paragraphs) and used < max_chars:
            p = paragraphs[i]
            text = _render_paragraph(p, context=False)
            if used + len(text) > max_chars and current:
                # Would overflow and we already have something in the
                # batch → flush.
                break
            current.append(p)
            used += len(text)
            i += 1

        batches.append(_Batch(entries=current, context=list(context)))
        # Set up overlap: the last _CONTEXT_OVERLAP paragraphs of this
        # batch become context for the next one.
        context = current[-_CONTEXT_OVERLAP:] if len(current) > _CONTEXT_OVERLAP else list(current)

    return batches


def _render_batch(batch: _Batch) -> str:
    """Render a batch into the text block sent to the LLM."""
    lines: list[str] = []
    for p in batch.context:
        lines.append(_render_paragraph(p, context=True))
    # Re-number the labeled entries from 0 for the model.
    for local_idx, p in enumerate(batch.entries):
        lines.append(_render_paragraph(p, context=False, local_index=local_idx))
    return "\n".join(lines)


def _render_paragraph(
    p: Paragraph, *, context: bool, local_index: int | None = None
) -> str:
    """Render one paragraph as a single line.

    Format: ``<idx>: <text>`` with a ``context_only:true`` prefix when
    carried over. Empty paragraphs containing an object get a hint
    ([image] / [table] / [formula]) so the model has something to go on.
    """
    text = p.text.strip()
    if not text:
        if p.has_image:
            text = _EMPTY_OBJECT_HINT["image"]
        elif p.has_table:
            text = _EMPTY_OBJECT_HINT["table"]
        elif p.has_formula:
            text = _EMPTY_OBJECT_HINT["formula"]

    idx = local_index if local_index is not None else p.index
    prefix = f"{_CONTEXT_PREFIX} " if context else ""
    return f"{prefix}{idx}: {text}"


def _parse_labels(raw: str) -> list[LabelEntry]:
    """Parse the LLM's JSON response into a list of LabelEntry.

    Each entry now carries an optional ``style`` dict (parsed into a
    :class:`ParagraphStyle`). Only non-None style fields are kept.

    Tolerates minor pollution: if the model wraps JSON in markdown
    fences or prepends prose, we extract the first ``{...}``` block.
    """
    text = raw.strip()
    if not text:
        return []

    # Strip markdown fences if present.
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
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []

    labels = data.get("labels") if isinstance(data, dict) else None
    if not isinstance(labels, list):
        return []

    entries: list[LabelEntry] = []
    for item in labels:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        role_str = item.get("role")
        conf = item.get("confidence", 0.0)
        if idx is None or role_str is None:
            continue
        try:
            role = Role(role_str)
        except ValueError:
            continue
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            conf_f = 0.0

        # Parse optional style dict. Only keep non-None fields; invalid
        # fields are dropped (the rest still applies).
        style_raw = item.get("style")
        style: ParagraphStyle | None = None
        if isinstance(style_raw, dict) and style_raw:
            # Filter out None values and construct the style.
            clean = {k: v for k, v in style_raw.items() if v is not None}
            if clean:
                try:
                    style = ParagraphStyle(**clean)
                except (ValueError, TypeError):
                    # If the AI returned a malformed style, skip it
                    # (the paragraph keeps its original formatting).
                    style = None

        entries.append(
            LabelEntry(index=int(idx), role=role, confidence=conf_f, style=style)
        )
    return entries
