# PaperGroom

> Turn an unformatted Word document into one that meets a strict thesis/dissertation
> formatting spec — with support for your own custom rules, which take precedence.

## The problem it solves

Formatting a thesis by hand is slow, repetitive, and easy to get wrong: heading
levels drift, line spacing is inconsistent, references don't follow the required
style. PaperGroom automates that.

The documents it targets are the ones whose **structure has already been lost** —
a paper drafted by an LLM and pasted into Word, or converted from PDF/HTML. In
those files, a heading and its body text are often a single paragraph, several
references get glued into one paragraph, and tables survive only as lines of
plain text. Recovering that structure is the core of the tool, not an afterthought.

## Current status: **mid-rework**

The pipeline runs end to end, and both structural faults are addressed. What
remains is breadth — tables, custom rulesets, review tooling — rather than
architecture. See [ROADMAP.md](ROADMAP.md) for the plan and the caveats.

1. ~~**The pipeline assumed one paragraph equals one semantic unit.**~~
   **Addressed.** A heading and its body, or several bibliography entries, are
   split into one paragraph per unit before anything styles them, with run
   formatting preserved.
2. ~~**The AI was asked to emit concrete style values.**~~ **Addressed.** The
   model now only picks a *role*. Styles come from a YAML ruleset, resolved
   deterministically afterwards — reproducible, unit-testable, and about 90%
   cheaper per batch, since the long prose specification is no longer sent.

Be careful with the numbers in ROADMAP.md: the fixtures were written by the
same hand as the rules, so they are a regression net rather than independent
evidence.

## Design principles

These are the invariants the rework is converging on:

- **Structure before style.** Recover the logical structure first; styling a
  wrong structure is wrong no matter how good the styling is.
- **The AI only makes semantic judgments.** It decides *what a paragraph is*
  (`title_l1`, `body`, `reference`, …) and nothing else. It never decides a font
  size. Styles come from a deterministic ruleset.
- **Rules are data, not code.** Formatting specs live in YAML; adding a template
  means writing a config, not changing code.
- **Your rules win.** A custom ruleset overrides the built-in one field by field
  — anything you don't specify is inherited.
- **Original objects are protected.** Images, equations, and field codes only
  ever get their surrounding paragraph properties changed, never their content.

## Requirements

- Python 3.10+
- An LLM API key (Volcengine Ark, OpenAI, or any OpenAI-compatible endpoint)

## Installation

```bash
git clone https://github.com/tb050304/PaperGroom.git
cd PaperGroom
pip install -e .
```

## Configure your API key

The repository contains no secrets. `.env` is git-ignored — put your real key there.

```bash
cp .env.example .env
```

Then edit `.env`. Pick one provider:

```env
LLM_PROVIDER=ark                              # ark | openai | local

# Volcengine Ark (stable access in China)
ARK_API_KEY=your_ark_api_key_here
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=your_endpoint_id_or_model_name

# OpenAI
# LLM_PROVIDER=openai
# OPENAI_API_KEY=your_openai_api_key_here
# OPENAI_MODEL=gpt-4o-mini

# Local model (Ollama / vLLM)
# LLM_PROVIDER=local
# LOCAL_BASE_URL=http://localhost:11434/v1
# LOCAL_MODEL=qwen2.5:7b
```

## Usage

```bash
# Format with the built-in thesis ruleset
papergroom process input.docx -o output.docx

# Format with your own ruleset (a YAML file)
papergroom process input.docx -r my_school.yaml -o output.docx

# Also map headings onto Word's built-in styles, so the navigation pane and
# an automatic table of contents work
papergroom process input.docx -o output.docx --word-styles

# Also dump the role and style decided for each paragraph
papergroom process input.docx -o output.docx --debug-annotation

# Check a ruleset without processing anything
papergroom validate-rules my_school.yaml
```

`--word-styles` is off by default because direct formatting is more
predictable. When it is on, headings get Word's built-in Heading 1/2/3 styles
in addition to the ruleset's formatting, and the theme colour those styles
carry is neutralised to black unless the ruleset sets a colour. The styles
are matched by name across English and Chinese, and by the id the document
actually uses — files from converters do not always call Heading 1
`Heading1`.

If `-o` is omitted, output goes to `<input>_formatted.docx` next to the input.

Only paragraphs the ruleset covers are restyled; anything the ruleset is
silent about keeps its original formatting.

Responses are cached under `.cache/papergroom/`, so re-running over the same
document is free until the prompt or the text changes. Set `LLM_CACHE_DIR`
to move it, or to an empty value to disable caching.

## Project structure

```
PaperGroom/
├── pyproject.toml
├── README.md
├── ROADMAP.md
├── .env.example                       # config template (no real secrets)
├── scripts/                           # dev-only diagnostics, not shipped
│   ├── diag_llm.py                    # raw LLM call, to debug connectivity
│   ├── dump_body_xml.py               # walk <w:body> children in document order
│   ├── dump_paragraphs.py             # dump parsed paragraph flags
│   ├── eval_segmenter.py              # score structure recovery vs fixtures
│   └── eval_roles.py                  # score role labeling (--live to call the API)
├── src/papergroom/
│   ├── cli.py                         # `papergroom process`
│   ├── config.py                      # .env loading, provider selection
│   ├── models.py                      # intermediate representation
│   ├── parser/docx_parser.py          # docx -> Paragraph list
│   ├── structure/                     # recover logical structure
│   │   ├── patterns.py                #   deterministic text rules
│   │   ├── segmenter.py               #   split a paragraph into units
│   │   └── apply.py                   #   replay the split on the XML
│   ├── ai/                            # role labeling
│   │   ├── prompts.py                 #   compact role guide (no styles)
│   │   ├── labeler.py                 #   patterns, then the model, then checks
│   │   ├── client.py                  #   OpenAI-compatible chat client
│   │   └── cache.py                   #   response cache
│   ├── rules/
│   │   ├── standard_thesis.yaml       # the built-in ruleset
│   │   ├── schema.py                  # ruleset model + field-by-field merge
│   │   ├── loader.py                  # loading, extends resolution
│   │   ├── validate.py                # sanity warnings
│   │   ├── resolve.py                 # role -> style, deterministically
│   │   ├── applier.py                 # style -> docx
│   │   └── default_thesis_rules.md    # prose reference; nothing reads it
│   └── writer/docx_writer.py          # save, track-changes off
└── tests/
    ├── fixtures/                      # expectations the harnesses score against
    └── test_*.py
```

## Security notes

- The repository contains **no API keys, no secrets, and no personal documents**
- All secret config goes through `.env`, which `.gitignore` excludes
- `.env.example` holds only `your_xxx_here` placeholders
- Outputs go to `output/`, also git-ignored
- If you ever commit a secret, rotate it immediately and purge the history
  ([GitHub's guide](https://docs.github.com/code-security/secret-scanning/removing-sensitive-data-from-a-repository))

## Custom rulesets

A ruleset is a YAML file. It can extend the built-in one and override only what
it cares about — the merge is per role, per field:

```yaml
name: my_school
extends: standard_thesis

styles:
  body:
    font_size_pt: 14      # changes only the size
  title_l1:
    alignment: center     # changes only the alignment
```

Everything not mentioned is inherited. In the example above `body` keeps its
宋体 font, justified alignment, 1.5 line spacing and 2-character indent from
the built-in ruleset; `title_l1` keeps 黑体, 16pt, bold, and its spacing.

`extends` takes a built-in name or a path (relative paths are resolved against
the extending file first). Chains work, and cycles are rejected.

Check a ruleset without processing anything:

```bash
papergroom validate-rules my_school.yaml
```

Misspelled properties and absurd values are rejected when the file is loaded;
an unknown role name is reported as a warning, because the style would
silently never match anything.

## License

MIT — see [LICENSE](LICENSE).
