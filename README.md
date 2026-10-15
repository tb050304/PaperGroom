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

The pipeline runs end to end, and structure recovery has landed. **The output
is still not good enough to rely on** — see [ROADMAP.md](ROADMAP.md) for the
plan and the reasoning.

The two root causes:

1. ~~**The pipeline assumes one paragraph equals one semantic unit.**~~
   **Addressed (Phase 1).** Documents often carry a heading and its body — or
   several bibliography entries — in a single paragraph. Those are now split
   into one unit per paragraph before anything tries to style them, with the
   original run formatting preserved.
2. **The AI is asked to emit concrete style values** (font sizes, spacing…)
   after reading a long prose rules document. Still open. That is
   non-deterministic, expensive, impossible to unit-test, and contradicts the
   design principles below. Phase 3 replaces it with a YAML ruleset.

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
# Format with the built-in thesis rules
papergroom process input.docx -o output.docx

# Format with your own rules (a .md or .txt file)
papergroom process input.docx -r my_school_rules.md -o output.docx

# Also dump what the AI decided for each paragraph
papergroom process input.docx -o output.docx --debug-annotation
```

If `-o` is omitted, output goes to `<input>_formatted.docx` next to the input.

> **Note:** the `-r` / `--rules` flag currently expects a prose rules file
> (`.md`/`.txt`), not the YAML ruleset. Wiring the CLI to the YAML ruleset is
> part of the rework (ROADMAP Phase 3). Until then, `standard_thesis.yaml` is
> loaded by the rule engine but is not what the CLI uses.

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
│   └── eval_segmenter.py              # score structure recovery vs fixtures
├── src/papergroom/
│   ├── cli.py                         # `papergroom process`
│   ├── config.py                      # .env loading, provider selection
│   ├── models.py                      # intermediate representation
│   ├── parser/docx_parser.py          # docx -> Paragraph list
│   ├── structure/                     # recover logical structure
│   │   ├── patterns.py                #   deterministic text rules
│   │   ├── segmenter.py               #   split a paragraph into units
│   │   └── apply.py                   #   replay the split on the XML
│   ├── ai/                            # client.py / prompts.py / labeler.py
│   ├── rules/
│   │   ├── applier.py                 # style application (deterministic)
│   │   ├── loader.py, schema.py       # YAML ruleset loading + validation
│   │   ├── rules_text.py              # loads the prose rules for the AI
│   │   ├── default_thesis_rules.md    # domain reference (see the note inside)
│   │   └── standard_thesis.yaml       # the executable ruleset
│   └── writer/docx_writer.py          # save, track-changes off
└── tests/
    ├── fixtures/segment_cases.yaml    # structure-recovery expectations
    └── test_*.py
```

## Security notes

- The repository contains **no API keys, no secrets, and no personal documents**
- All secret config goes through `.env`, which `.gitignore` excludes
- `.env.example` holds only `your_xxx_here` placeholders
- Outputs go to `output/`, also git-ignored
- If you ever commit a secret, rotate it immediately and purge the history
  ([GitHub's guide](https://docs.github.com/code-security/secret-scanning/removing-sensitive-data-from-a-repository))

## Contributing rulesets

Once the rework reaches Phase 3, a ruleset is a YAML file that can `extends` the
built-in one and override only the fields you care about. That flow doesn't exist
yet — described here so the target is clear, not as a current capability.

## License

MIT — see [LICENSE](LICENSE).
