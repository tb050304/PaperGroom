"""Score the structure-recovery segmenter against the fixture set.

Run after changing any rule in ``papergroom/structure/``:

    python scripts/eval_segmenter.py

Three numbers come out:

* **segments** — fraction of cases where the exact sequence of segments
  matched. The headline number; the Phase 1 target is 95%.
* **boundaries** — precision/recall over split positions. Catches partial
  mistakes that the exact-match number would hide: a case that split in the
  right place *and* one place too many scores 0 on segments but shows up
  here as a precision loss.
* **roles** — fraction of segments whose deterministic role hint matched.

Exits non-zero when the segment score is below target, so it can gate CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papergroom.structure.segmenter import segment_text  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "segment_cases.yaml"
TARGET = 0.95


def expected_boundaries(text: str, expected: list[str]) -> set[int]:
    """Where the expected segments start, as offsets into ``text``.

    Segments are located by searching forward, so dropped separators (the
    colon in "摘要：……") do not confuse the offsets.
    """
    bounds: set[int] = set()
    cursor = 0
    for piece in expected:
        try:
            at = text.index(piece, cursor)
        except ValueError:
            raise SystemExit(
                f"fixture error: segment {piece!r} does not appear in {text!r}"
            ) from None
        if at > 0:
            bounds.add(at)
        cursor = at + len(piece)
    return bounds


def main() -> int:
    cases = yaml.safe_load(FIXTURES.read_text(encoding="utf-8"))["cases"]

    segment_hits = 0
    role_hits = 0
    role_total = 0
    tp = fp = fn = 0
    failures: list[str] = []

    for case in cases:
        text = case["text"]
        expected = case["expect"]
        want_texts = [e["text"] for e in expected]
        want_roles = [e.get("role") for e in expected]

        got = segment_text(text)
        got_texts = [s.text for s in got]
        got_roles = [s.role_hint.value if s.role_hint else None for s in got]

        if got_texts == want_texts:
            segment_hits += 1
        else:
            failures.append(
                f"  text:     {text!r}\n"
                f"  expected: {want_texts}\n"
                f"  got:      {got_texts}"
            )

        want_b = expected_boundaries(text, want_texts)
        got_b = {s.start for s in got if s.start > 0}
        tp += len(want_b & got_b)
        fp += len(got_b - want_b)
        fn += len(want_b - got_b)

        if len(got_roles) == len(want_roles):
            role_total += len(want_roles)
            role_hits += sum(g == w for g, w in zip(got_roles, want_roles))

    n = len(cases)
    segment_score = segment_hits / n
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    role_score = role_hits / role_total if role_total else 0.0

    if failures:
        print(f"--- {len(failures)} failing case(s) ---")
        for f in failures:
            print(f)
            print()

    print(f"cases            {n}")
    print(f"segments         {segment_score:6.1%}   ({segment_hits}/{n})   target {TARGET:.0%}")
    print(f"boundary P/R/F1  {precision:6.1%} / {recall:.1%} / {f1:.1%}   (tp={tp} fp={fp} fn={fn})")
    print(f"roles            {role_score:6.1%}   ({role_hits}/{role_total})")

    if segment_score < TARGET:
        print(f"\nFAIL: segment score {segment_score:.1%} is below target {TARGET:.0%}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
