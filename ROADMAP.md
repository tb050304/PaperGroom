# PaperGroom Development Roadmap

This roadmap breaks PaperGroom into 5 stages, evolving from a minimum viable version to a complete open-source tool.

> Stages are independent of each other; each stage produces something that can run and be released on its own. It is recommended to proceed in order and only move to the next stage once the previous one is stable.

---

## Stage 0: Project Skeleton (Done)

**Goal**: Set up an open-source, collaboration-friendly, leak-proof project base.

- [x] Initialize git repo and directory structure
- [x] `.gitignore` excluding secrets, virtualenvs, and output files
- [x] `.env.example` config template (no real secrets)
- [x] README.md describing project purpose and local setup
- [x] ROADMAP.md
- [x] MIT License

**Output**: An empty-shell repository ready to clone and run.

---

## Stage 1: MVP Core Pipeline

**Goal**: Run the end-to-end flow of `import docx → AI structure labeling → rule engine applies styles → export docx`.

### 1.1 docx Parser Layer (`src/papergroom/parser/`)
- [ ] Read paragraphs, Runs, styles (`w:pPr` / `w:rPr`)
- [ ] Extract images (`w:drawing`), tables, formulas (OMML)
- [ ] Output a unified intermediate structure (paragraph list + role + original style)

### 1.2 AI Structure Labeling Layer (`src/papergroom/ai/`)
- [ ] Design the role label set: `title_l1` / `title_l2` / `body` / `figure` / `figure_caption` / `table_caption` / `reference` / `abstract` / `formula` ...
- [ ] LLM prompt + few-shot examples
- [ ] Call per segment and merge results
- [ ] Support configurable model provider (Ark / OpenAI / local)

### 1.3 Rule Engine (`src/papergroom/rules/`)
- [ ] Define YAML rule format (role → style mapping)
- [ ] Rule loader and validator
- [ ] Rule applier: modify `Paragraph` / `Run` styles by role

### 1.4 docx Writer Layer (`src/papergroom/writer/`)
- [ ] Apply styles via python-docx
- [ ] Protect field objects, formulas, and images from corruption
- [ ] Output with track changes disabled

### 1.5 CLI Entry (`src/papergroom/cli.py`)
- [ ] `papergroom process <input.docx> -r <rules.yaml> -o <output.docx>`
- [ ] `papergroom list-rules`

### 1.6 Built-in Standard Thesis Ruleset
- [ ] `rules/standard_thesis.yaml` (referencing GB/T 7714 and common thesis specs)

**Output**: After `pip install -e .`, a paper can be processed from the command line and exported as a docx that conforms to the default format.

**Completion Criteria**: For a typical paper, correctly identify 80%+ of paragraph roles and apply the corresponding styles.

---

## Stage 2: Ruleset Ecosystem

**Goal**: Make "formatting rules" a shareable, reusable resource.

- [ ] Built-in rulesets: GB/T 7714, STEM thesis, humanities & social sciences thesis, journal submission templates
- [ ] Rule editing documentation and field reference
- [ ] Rule validator: detect missing fields, out-of-range values, conflicts
- [ ] Rule preview: show the applied effect on a sample document (screenshots or diff report)
- [ ] Custom rules directory support (`--rules-dir`)

**Output**: Users can contribute their own rulesets to `rules/community/`.

---

## Stage 3: Accuracy and Human Review

**Goal**: Address formatting errors caused by AI mislabeling.

- [ ] AI labeling confidence output
- [ ] Labeling result visualization report (HTML, highlighting each paragraph's role)
- [ ] Human correction interface (modify the YAML annotation file and reapply styles)
- [ ] Few-shot example library (categorized by discipline)
- [ ] Formula / complex table protection strategy (skip style reflow after detection)
- [ ] Cross-reference, table of contents, page-number field protection

**Output**: Accuracy improved from 80% to 95%+, with a human fallback entry.

---

## Stage 4: Web UI and Batch Processing

**Goal**: Lower the usage barrier; support non-technical users and batch scenarios.

- [ ] Web UI: drag-and-drop upload, select rules, preview, download
- [ ] Batch processing: directory scan + concurrency
- [ ] Processing history and result comparison
- [ ] Multi-model provider switching (Ark / OpenAI / local models)
- [ ] Deployment documentation (Docker, local deployment)

**Output**: A deployable web service that supports multiple users.

---

## Stage 5: Community and Ecosystem

**Goal**: Establish a sustainable contribution mechanism.

- [ ] Ruleset marketplace (community-contributed rulesets, with ratings and compatibility notes)
- [ ] Plugin mechanism (custom parsers, custom AI labelers)
- [ ] Internationalization (English paper formats, other languages)
- [ ] Documentation site
- [ ] Contributor guide (CONTRIBUTING.md)

**Output**: An open-source project with an active community.

---

## Contribution Priority

If this is your first contribution, consider starting with:

1. Any sub-module of Stage 1 (parser / labeler / rules / writer)
2. New rulesets in Stage 2 (no code required, just understanding of format specs)
3. Few-shot example contributions in Stage 3

See [CONTRIBUTING.md](CONTRIBUTING.md) for the detailed contribution process (to be added after Stage 1).
