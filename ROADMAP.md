# PaperGroom Development Roadmap

**Goal:** take an unformatted Word document and produce one that meets a strict
thesis formatting spec, with user-supplied rules taking precedence over the
built-in ones.

## Where we are

- **Skeleton** — done (repo, packaging, config, docs).
- **Stage 1 prototype** — done, runs end to end, but quality is not acceptable.
  Preserved in history as a checkpoint commit.
- **Phase 1 — structure recovery** — built and wired in. Paragraphs that hold
  more than one semantic unit are split before anything tries to style them.
  See Phase 1 for what is still open.
- **Phase 2 — role labeling** — built and wired in. The model now only picks a
  role; styles come from the ruleset through a deterministic resolver. Not yet
  measured against a real model — see Phase 2.
- **Phase 3 onward** — not started.

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

**Built**

- `structure/segmenter.py` — pure text → segments, applied recursively so rules
  compose (a chapter heading whose body holds the whole bibliography splits
  twice: once at the heading, again between entries)
- `structure/patterns.py` — the rule catalog: merged heading + body, a section
  word glued on with a colon, merged bibliography entries, caption role hints
- `structure/apply.py` — character-level splitting of the real XML, cloning
  runs so run formatting survives; paragraphs carrying an image, equation or
  hyperlink are never split; source paragraphs are processed right-to-left so
  indices cannot drift (the previous attempt went forwards and emitted
  operations for paragraphs that did not exist)
- `tests/fixtures/segment_cases.yaml` + `scripts/eval_segmenter.py` — 26 cases
  scored three ways: segment sequence, boundary precision/recall, role hints
- Wired into the CLI, with a writer-side guard that refuses to write when the
  model and the file disagree rather than silently mis-styling

**Measured:** 26/26 fixtures · boundary P/R/F1 100% · role hints 39/39.

> **Caveat.** Those fixtures were written by the same hand as the rules, so
> they are a regression net, not independent evidence. The edge cases were
> chosen adversarially — cover-page colons, inline citations, years, numbered
> lists, multi-word Latin headings — and two of them exposed genuine bugs, but
> the score is not yet a quality claim. Real confidence needs documents the
> rules have never seen.

**Deferred — pseudo-table recovery.** Rebuilding a table that survives only as
a line of space-separated text (`排版方式 平均耗时 (min) 格式正确率 (%) 人工排版
27.3 81.2 …`) requires inferring the column count from content. That is
substantially harder and much rarer than heading/reference splitting, and a
false positive would silently mangle ordinary prose. It gets its own phase
instead of riding along here.

**Still open**

- AI fallback for paragraphs the regexes cannot decide (a heading with no
  separator before its body: `第1章 绪论本文研究的背景……`)
- Chinese ordinal headings (`一、引言`) — needs rules validated against real
  documents before it is safe to guess
- A heading containing an internal space (`1 研究 背景 当前……`) splits at the
  first space, not the last; no deterministic signal distinguishes it

**Exit criterion:** the harness holds ≥ 95% as documents it has never seen are
added to the fixture set.

### Phase 2 — Role labeling: the model classifies, nothing else

**Built**

- `ai/prompts.py` rewritten. The model returns `{index, role, confidence}` and
  nothing else; the 878-line prose specification it used to read is replaced by
  a compact role guide plus a style summary **derived from the YAML**, so it
  cannot drift from what the applier actually does. **~8,400 → ~840 tokens per
  batch.**
- Three layers with strict precedence: patterns decide what they can and never
  reach a model at all; the model decides the rest; the pattern decisions are
  re-asserted afterwards, so nothing the model says can override them.
- `structure/patterns.py::certain_role` draws that boundary deliberately narrow.
  Numbered headings stay out — telling "1 数据收集" (a heading) from a list item
  needs the surrounding document, so they go to the model as a *hint*.
- Table-of-contents entries are spotted by their leader dots and never styled
  as headings, though they are shaped exactly like them.
- `rules/resolve.py` — role → style, deterministic. This is the half the model
  never touches.
- Response caching under `.cache/papergroom/`. The client is built lazily, so a
  document the patterns fully account for needs no API key at all.

**Measured (offline):** 22 role fixtures — 6 settled by pattern with zero
errors, 16 left to the model. 169 tests pass.

**Not yet measured:** the model's own accuracy. That needs
`scripts/eval_roles.py --live`, which calls the real API. Until then the ≥95%
target is **unverified**, and the fixtures were written by the same hand as the
rules, so even a good score would be weak evidence on its own.

**Landed here, out of sequence:** the built-in ruleset was completed —
`document_title` was missing entirely, and `body`, the most common role by far,
had no font and no line spacing — with its values reconciled against the prose
spec. The style bridge could not produce sane output otherwise.

### Phase 3 — Rules engine and style application

Partially landed early, because Phase 2 could not produce sane output without
it: the built-in ruleset is now complete and reconciled with the prose spec,
and `rules/resolve.py` connects roles to styles deterministically.

**Remaining**

- **`extends` + per-field override.** A custom ruleset must be able to change
  one property of one role and inherit the rest. This is the "your rules win"
  requirement and it does not exist yet — today a custom ruleset is an
  all-or-nothing replacement.
- Harden the applier: idempotent, handles paragraphs inside tables, and a
  `--word-styles` opt-in that maps headings onto Word's built-in styles so the
  navigation pane and an automatic table of contents work.
- A ruleset validator: out-of-range values, roles in the taxonomy but missing
  from the ruleset, conflicting settings.
- A style field for a *negative* first-line indent, so bibliography entries can
  get a true hanging indent rather than the block indent they have now.
- Delete `default_thesis_rules.md` once the YAML carries its reasoning too.

**Done when:** applied styles match the ruleset field-for-field at 100%
(deterministic, so this is an assertion rather than an estimate), and a custom
ruleset that sets one property changes exactly that one property.

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
