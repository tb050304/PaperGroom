# PaperGroom Development Roadmap

**Goal:** take an unformatted Word document and produce one that meets a strict
thesis formatting spec, with user-supplied rules taking precedence over the
built-in ones.

## Where we are

- **Skeleton** — done (repo, packaging, config, docs).
- **Stage 1 prototype** — done, runs end to end, but quality is not acceptable.
  Kept on `main` as a checkpoint commit so nothing is lost.
- **Rework** — starts now. Phases below.

## Why the prototype isn't good enough

Diagnosed against a real target document (an LLM-drafted paper pasted into Word:
11 paragraphs, all `Normal`, no alignment, no indents, 0 real tables, 0 images):

```
[3]  1 研究背景 当前高校课程论文、毕业设计均有严格统一的格式规范……   ← heading + body in ONE paragraph
[6]  2 系统实验分析 …… 排版方式 平均耗时 (min) 格式正确率 (%) ……      ← a table degraded to a line of text
[9]  [1] 李华。…… [2] 张强。……                                      ← two references in ONE paragraph
```

1. **The pipeline assumes one paragraph == one semantic unit.** For the target
   input it isn't. This is why the output is wrong no matter how well the AI
   labels: a paragraph that is a heading *plus* its body cannot be styled
   correctly as a single unit. The previous `structurizer/` attempt at fixing
   this was removed — it was unreferenced and measurably wrong (off-by-one
   splits, splitting mid-name, missed detections, and a crash on call).
2. **The AI is asked to emit concrete style values.** It reads a long prose
   rules document and outputs 12 style fields per paragraph. That is
   non-deterministic (the same role gets different sizes in different
   paragraphs), expensive (the whole rules document is resent with every batch),
   and untestable. It also contradicts the project's own stated principle.
3. **There is no measurement.** No fixtures, no scoring. Without a number,
   "the output is bad" can't be turned into progress.
4. **Two conflicting sources of truth.** The prose rules and `standard_thesis.yaml`
   disagree on real values (see the status note in `default_thesis_rules.md`).

## Target architecture

Separate *judgment* from *application*. Each layer does one job and is testable alone.

```
input.docx
  │
  ├─ A. Structure Recovery     deterministic first, AI only as fallback
  │     split glued blocks into one-semantic-unit blocks;
  │     detect pseudo-tables and pseudo-lists
  │
  ├─ B. Role Labeling          AI, emits role + confidence ONLY
  │     sliding-window batching + deterministic post-checks
  │
  ├─ C. Rule Resolution        YAML, layered: built-in ← user (per-field override)
  │
  └─ D. Style Application      100% deterministic
        → output.docx + a review report
```

### Invariants

1. **Structure before style.** A wrong structure can't be styled right.
2. **The AI only classifies.** `role` + `confidence`. Never a font size.
3. **Everything is measurable.** Every change is justified by a number on the fixture set.
4. **Original objects are protected.** Images, equations (OMML), field codes:
   outer paragraph properties only, never content.

### Rule layering (this is how "your rules win" works)

Merge granularity is **role → field**:

```yaml
# built-in: src/papergroom/rules/standard_thesis.yaml
styles:
  body: {font_name_east_asian: 宋体, font_size_pt: 12, alignment: justify, first_line_indent_chars: 2}
```
```yaml
# user: my_school.yaml — only what you want changed
extends: standard_thesis
styles:
  body: {font_size_pt: 14}      # only the size; everything else inherited
```
Result: `body` = 宋体 / **14pt** / justified / 2-char indent.

The authoritative format for custom rules is **YAML**. A later "rules assistant"
may let users describe requirements in natural language and have the AI draft
the YAML — but the user reviews it, and application stays deterministic.

### How styles land in Word

**Default is direct formatting** (paragraph/run properties). It is predictable,
doesn't depend on the target template, and avoids theme side effects (Word's
built-in *Heading 1* is blue with a border by default). The cost is that the
output carries no semantic styles, so Word's navigation pane and auto-TOC won't
work. A `--word-styles` opt-in is planned rather than being the default.

---

## Phases

Each phase ships something runnable, and is judged by a number, not a feeling.

### Phase 1 — Structure recovery engine + evaluation harness ⭐

Highest priority: the target input is a document whose structure is already gone.

- **Block splitting**, deterministic regex first: heading numbering
  (`^第N章` / `^N ` / `^N.M` / `^N.M.K` / `一、`), references (`^\[\d+\]`),
  captions (`^图\d` / `^表\d`), pseudo-lists
- **Pseudo-table detection**: consecutive lines sharing a delimiter structure
  (tabs / runs of spaces) rebuilt as real Word tables
- **AI only as fallback** — for paragraphs the regexes can't decide
- **Character-level splitting with run cloning**, preserving run-level formatting
- **Evaluation harness**: 5–8 synthetic fixtures under `tests/fixtures/` covering
  each degradation mode + expected block structure + a scoring script

**Done when:** block-split accuracy ≥ 95% on the fixture set, reproducible by script.

### Phase 2 — Role labeling (AI, classification only)

- Rewrite the prompt to emit `{index, role, confidence}` only, injecting a
  **compact role summary derived from the YAML** instead of the long prose rules
- Keep the existing sliding-window batcher (`ai/labeler.py`) — it's the healthiest
  part of the current code
- **Deterministic post-checks**: `^\[\d+\]` inside the references section is a
  `reference`, regardless of what the model said
- Cache responses so re-runs don't re-bill

**Done when:** role accuracy ≥ 95% on the fixture set, at an order of magnitude
lower cost than today.

### Phase 3 — Rules engine and style application

- Finalize the YAML schema and implement `extends` + per-field override
- Adjudicate the prose-vs-YAML conflicts **by hand**, port the agreed values into
  the YAML, then delete `default_thesis_rules.md`
- Harden the applier: idempotent, handles paragraphs inside tables, `--word-styles` opt-in
- Ruleset validator: out-of-range values, missing roles, level conflicts

**Done when:** applied styles match the ruleset field-for-field at 100%
(deterministic, so this is an assertion, not an estimate).

### Phase 4 — Review loop

- HTML report: role highlighting, confidence, before/after diff
- Export labels → correct by hand → re-run only the affected parts

**Done when:** a person can find and fix every misclassification in one paper
within 5 minutes.

### Phase 5 — Polish and usability

- CLI: `list-rules`, `--dry-run`, batch directory processing
- Rules assistant (natural language → YAML draft → user confirms)
- Error handling, documentation, release

---

## How we measure

Every phase ends with numbers produced by the harness, not by impression:

| Metric | Target |
|---|---|
| Block-split accuracy (Phase 1) | ≥ 95% |
| Role accuracy (Phase 2) | ≥ 95% |
| Style conformance vs ruleset (Phase 3) | 100% (asserted) |
| Images / equations / fields altered | 0 (asserted) |

## Out of scope for now

Web UI, multi-user deployment, a ruleset marketplace — revisit after Phase 4.
