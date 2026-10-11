# Stage 1 Implementation Plan: MVP Core Pipeline

## Context

PaperGroom is at Stage 0 (skeleton only — 6 docs, no code). Stage 1 must deliver the end-to-end MVP: `import docx → parse → AI labels paragraph roles → rule engine applies styles → export docx`, runnable via `papergroom process input.docx -o output.docx`.

Key decisions confirmed with user:
- **LLM client**: `openai` SDK as unified client (Ark/OpenAI/local all speak OpenAI-compatible protocol)
- **CLI**: `typer`
- **Labeling granularity**: sliding-window batch (pack paragraphs to a token budget, call once per batch, carry boundary context between batches)

This plan produces a runnable `pip install -e .` package with one built-in ruleset.

## Target Structure

```
PaperGroom/
├── pyproject.toml              # PEP 621, setuptools backend
├── src/papergroom/
│   ├── __init__.py
│   ├── cli.py                  # typer entry: process / list-rules
│   ├── config.py               # env loading (LLM_PROVIDER, keys, model)
│   ├── parser/
│   │   ├── __init__.py
│   │   └── docx_parser.py      # python-docx → Paragraph list
│   ├── models.py               # pydantic data models (Paragraph, Role, Annotation)
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── client.py           # openai SDK wrapper, provider-agnostic
│   │   ├── prompts.py          # role label set + system prompt + few-shot
│   │   └── labeler.py          # sliding-window batch labeling
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── schema.py           # pydantic schema for YAML rulesets
│   │   ├── loader.py           # load + validate YAML
│   │   └── applier.py          # role → style application on Paragraph/Run
│   └── writer/
│       ├── __init__.py
│       └── docx_writer.py     # python-docx style write-back, protect fields/images
├── rules/
│   └── standard_thesis.yaml   # built-in ruleset (GB/T 7714 + common thesis)
├── tests/
│   ├── fixtures/
│   │   └── sample.docx         # small test paper
│   ├── test_parser.py
│   ├── test_labeler.py        # mock LLM
│   └── test_applier.py
└── (existing: README.md, ROADMAP.md, .env.example, etc.)
```

## Module Design

### 1. `pyproject.toml` — packaging
- Backend: `setuptools>=68`, PEP 621 metadata
- Python `>=3.10`
- Deps: `python-docx>=1.1`, `openai>=1.40`, `pydantic>=2`, `typer>=0.12`, `pyyaml>=6`, `python-dotenv>=1`
- Console script: `papergroom = "papergroom.cli:app"`
- Dev deps (optional extra `dev`): `pytest>=8`, `pytest-mock`

### 2. `models.py` — intermediate representation
Pydantic models:
- `Role` enum: `title_l1, title_l2, title_l3, body, figure, figure_caption, table, table_caption, reference, abstract, formula, list_item, quote, unknown`
- `Paragraph`: `index, text, role, style_hint, has_image, has_table, has_formula, original_pPr_xml`
- `Annotation`: list of (index, role, confidence)

### 3. `parser/docx_parser.py`
- Use `python-docx` to iterate `document.paragraphs`
- For each paragraph capture: text, existing style id, alignment, runs, and flags for `w:drawing` / `w:tbl` adjacency / `m:oMath` (via lxml on `_p.xml`)
- Preserve original `<w:pPr>` XML string for the writer to restore if needed
- Tables handled as a unit (one Paragraph entry with role=`table`)

### 4. `ai/client.py`
- `OpenAIClient` wrapping `openai.OpenAI` (base_url + api_key from config)
- One method: `complete(messages, model, temperature=0, response_format="json_object")`
- Reads config from `config.py` (provider switch → picks the matching base_url/key/model triple)

### 5. `ai/prompts.py`
- `SYSTEM_PROMPT`: explain task, output strict JSON `{"labels":[{"index":0,"role":"body","confidence":0.9}]}`
- Role label set with definitions
- 2–3 few-shot examples covering title/body/figure caption/reference

### 6. `ai/labeler.py` — sliding window
- Token budget per batch: `MAX_TOKENS_PER_BATCH` (default 6000, leaves room for response)
- Greedy pack: add paragraphs until budget hit; never split a paragraph
- Overlap: carry last 1–2 paragraphs of previous batch as context (marked `context_only:true` so they aren't re-labeled)
- Call client, parse JSON, merge into Annotation
- Confidence below `MIN_CONFIDENCE=0.6` → role stays `unknown` (writer leaves paragraph untouched)

### 7. `rules/schema.py` + `loader.py`
Pydantic schema for YAML:
```yaml
name: standard_thesis
version: 1
defaults:
  font_name: Times New Roman
  font_name_east_asian: 宋体
  font_size_pt: 12
  line_spacing: 1.5
styles:
  title_l1:
    font_size_pt: 16
    bold: true
    alignment: center
    space_before_pt: 24
    space_after_pt: 18
  body:
    first_line_indent_chars: 2
    alignment: justify
  figure_caption:
    font_size_pt: 10.5
    alignment: center
  # ...
```
Loader: resolves `rules/standard_thesis.yaml` from package data or `--rules` path; validates via pydantic.

### 8. `rules/applier.py`
- For each Paragraph: look up role in ruleset; if missing, fall back to `defaults`
- Apply to python-docx objects: `paragraph.style`, `paragraph.paragraph_format` (alignment, line spacing, space before/after, first-line indent), and per-Run `font.name/size/bold`
- East Asian font: set via `rPr/rFonts` XML (python-docx doesn't expose east-asia font directly)
- **Protected objects**: paragraphs containing `m:oMath` or being part of a table → only outer paragraph style changes, inner content untouched
- **Field codes** (`w:fldSimple`, `w:instrText`): never touched

### 9. `writer/docx_writer.py`
- Take the annotated + styled `Document` object, save to output path
- Ensure track changes off (`settings.xml` `w:trackChanges` removed)
- Write with `python-docx` `doc.save()`

### 10. `cli.py`
```
papergroom process <input> [-r RULES] [-o OUTPUT] [--debug-annotation]
papergroom list-rules
```
- `process`: parse → label → apply → write; `--debug-annotation` dumps `output/<name>.annotations.json`
- `list-rules`: lists built-in + `--rules-dir` rulesets

### 11. `rules/standard_thesis.yaml`
Built-in ruleset covering: title L1/L2/L3, body, abstract, figure caption, table caption, references, list item, quote. Values per common thesis spec.

## Implementation Order

1. `pyproject.toml` + package skeleton + `config.py` — pip installable
2. `models.py` + `parser/docx_parser.py` — get Paragraph list from a real docx
3. `rules/schema.py` + `loader.py` + `standard_thesis.yaml` — ruleset loadable
4. `rules/applier.py` + `writer/docx_writer.py` — apply styles, save docx (test with a hand-labeled fixture, no AI yet)
5. `ai/client.py` + `prompts.py` + `labeler.py` — plug in AI
6. `cli.py` — wire everything
7. `tests/` — parser, applier (mock LLM for labeler)

This order lets each layer be tested independently; AI is the least stable piece, so it lands last.

## Verification

End-to-end test on `tests/fixtures/sample.docx`:
1. `pip install -e .[dev]`
2. Set up `.env` with a real Ark key (or OpenAI)
3. `papergroom process tests/fixtures/sample.docx -o output/sample_out.docx --debug-annotation`
4. Open `output/sample_out.docx` — visually verify: H1/H2 styled, body justified + first-line indent, captions centered
5. Check `output/sample.annotations.json` — roles look reasonable
6. `pytest` — unit tests pass (parser, applier; labeler uses mock)

Completion criteria (from ROADMAP): ≥80% paragraph roles correctly identified on a typical paper, styles applied without corrupting images/formulas/fields.

## Out of Scope for Stage 1

- Web UI, batch processing (Stage 4)
- Human review UI (Stage 3)
- Multiple built-in rulesets (Stage 2) — only `standard_thesis.yaml`
- Confidence-based interactive correction (Stage 3) — low-confidence just leaves paragraph untouched
