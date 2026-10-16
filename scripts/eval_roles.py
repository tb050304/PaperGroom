"""Score role assignment against the fixtures.

    python scripts/eval_roles.py           # offline: the pattern layer only
    python scripts/eval_roles.py --live    # end to end, calls the real API

Offline reports how much of the work needs no model at all, and checks that
the patterns are right about what they *do* claim. It cannot tell you whether
the model is any good — only ``--live`` can, because only ``--live`` asks it.

``--live`` runs the real pipeline over the fixture paragraphs and scores the
final roles. It costs API calls; responses are cached, so re-runs are free
until the prompt or the text changes.

Target: 95% of paragraphs given the right role.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papergroom.models import Document, Paragraph, Role  # noqa: E402
from papergroom.structure.patterns import certain_role  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "role_cases.yaml"
TARGET = 0.95


def _load() -> list[dict]:
    return yaml.safe_load(FIXTURES.read_text(encoding="utf-8"))["cases"]


def offline(cases: list[dict]) -> int:
    """Report what the patterns resolve, and whether they resolve it right."""
    claimed = 0
    wrong: list[str] = []

    for case in cases:
        got = certain_role(case["text"])
        if got is None:
            continue
        claimed += 1
        if got != Role(case["role"]):
            wrong.append(f"  {case['text'][:50]!r}\n    expected {case['role']}, got {got.value}")

    n = len(cases)
    print(f"cases                     {n}")
    print(f"settled by pattern        {claimed}  ({claimed / n:.0%})")
    print(f"left to the model         {n - claimed}  ({(n - claimed) / n:.0%})")
    print()

    if wrong:
        print(f"--- {len(wrong)} pattern(s) claimed the wrong role ---")
        for w in wrong:
            print(w)
        print("\nFAIL: a pattern claimed a role it should not have.")
        return 1

    print("PASS: every paragraph the patterns claimed was claimed correctly.")
    print("      Run with --live to measure the model's own accuracy.")
    return 0


def live(cases: list[dict]) -> int:
    from papergroom.ai.labeler import label_document
    from papergroom.config import get_llm_config, get_processing_config
    from papergroom.rules.loader import load_ruleset

    doc = Document(
        source_path=str(FIXTURES),
        paragraphs=[Paragraph(index=i, text=c["text"]) for i, c in enumerate(cases)],
    )
    label_document(doc, get_llm_config(), load_ruleset("standard_thesis"), get_processing_config())

    hits = 0
    failures: list[str] = []
    for case, para in zip(cases, doc.paragraphs):
        if para.role.value == case["role"]:
            hits += 1
        else:
            failures.append(
                f"  {case['text'][:50]!r}\n"
                f"    expected {case['role']}, got {para.role.value} "
                f"(confidence {para.confidence:.2f})"
            )

    n = len(cases)
    score = hits / n
    if failures:
        print(f"--- {len(failures)} mislabel(s) ---")
        for f in failures:
            print(f)
        print()

    print(f"cases            {n}")
    print(f"role accuracy    {score:6.1%}   ({hits}/{n})   target {TARGET:.0%}")

    if score < TARGET:
        print(f"\nFAIL: role accuracy {score:.1%} is below target {TARGET:.0%}")
        return 1
    print("\nPASS")
    return 0


def main() -> int:
    cases = _load()
    return live(cases) if "--live" in sys.argv[1:] else offline(cases)


if __name__ == "__main__":
    raise SystemExit(main())
