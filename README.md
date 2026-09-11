# PaperGroom

> AI-powered Word document formatter: import a document + import formatting rules, export a spec-compliant docx.

## Introduction

PaperGroom tackles the tedious, repetitive task of adjusting paper / document formatting.

Its workflow is:

```
import docx → parse structure → AI labels each paragraph's role (title / body / figure caption / reference ...)
           → apply styles via rule engine → export a spec-compliant docx
```

Core design principles:

- **Formatting rules are decoupled from code**: rules live in YAML; adding a new template only requires a new config, not code changes
- **AI only does semantic labeling, never applies formatting directly**: style application goes through a deterministic rule engine, avoiding LLM output instability
- **Original objects are protected**: images, formulas, and field objects only get their styles changed, never their content, to prevent corruption

A standard ruleset referencing GB/T 7714 and common thesis specifications is bundled by default.

## Current Status

This project is at **Stage 0: project skeleton**. Core features are under development.

See [ROADMAP.md](ROADMAP.md) for the full development plan.

## Quick Start (once development is ready)

> The repository currently contains only the project skeleton. The core pipeline of Stage 1 is not yet complete. The usage below is planned to help you understand the workflow in advance.

### Requirements

- Python 3.10+
- An LLM API (for AI structure recognition)

### Installation

```bash
git clone https://github.com/tb050304/PaperGroom.git
cd PaperGroom
pip install -e .
```

### Configure Your API Key (Important)

This project requires an LLM API Key for document structure recognition. **The repository does not, and should not, contain any real secrets.**
Follow these steps to replace it with your own:

1. Copy the config template:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your own keys:

   ```env
   # Pick one provider; comment out the ones you don't use
   LLM_PROVIDER=ark  # options: ark | openai | local

   # Volcengine Ark (recommended; stable access in China, plan quotas can reduce cost)
   ARK_API_KEY=your_ark_api_key_here
   ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
   ARK_MODEL=your_endpoint_id_or_model_name

   # OpenAI (if used)
   # OPENAI_API_KEY=your_openai_api_key_here
   # OPENAI_BASE_URL=https://api.openai.com/v1
   # OPENAI_MODEL=gpt-4o-mini
   ```

3. `.env` is already in `.gitignore` and will **never be committed to git**. Feel free to put real keys in it.

### Usage

```bash
# Process a document with the default built-in rules
papergroom process input.docx -o output.docx

# Specify a ruleset
papergroom process input.docx -r rules/standard_thesis.yaml -o output.docx

# List built-in rules
papergroom list-rules
```

## Project Structure

```
PaperGroom/
├── README.md                  # this file
├── ROADMAP.md                 # development roadmap
├── .gitignore                 # git ignore rules (includes .env and other secret files)
├── .env.example               # config template (no real secrets, safe to commit)
├── LICENSE                    # MIT
├── rules/                     # formatting rulesets (YAML)
│   └── standard_thesis.yaml   # built-in standard thesis rules
├── src/papergroom/            # source code
│   ├── parser/                # docx parsing layer
│   ├── ai/                    # AI structure labeling layer
│   ├── rules/                 # rule engine
│   ├── writer/                # docx writer layer
│   └── cli.py                 # CLI entry
└── tests/
```

## How to Contribute Your Own Formatting Rules

Once Stage 1 is complete, you can:

1. Create a new YAML file under `rules/`, modeled on `standard_thesis.yaml`
2. Define the style for each role (font size, line spacing, alignment, indentation, etc.)
3. Test with `papergroom process --rules your_rules.yaml`
4. Open a PR to merge into `rules/community/`

For ruleset field definitions and examples, see [docs/rules.md](docs/rules.md) (to be added during Stage 1).

## Development Roadmap

See [ROADMAP.md](ROADMAP.md). It is split into 5 stages:

1. **Stage 1**: MVP core pipeline (parse → label → rules → write)
2. **Stage 2**: Ruleset ecosystem (multiple built-in rulesets, custom rules)
3. **Stage 3**: Accuracy and human review
4. **Stage 4**: Web UI and batch processing
5. **Stage 5**: Community and ecosystem

## Security Notes

- The repository **does not contain any real API keys / secrets / personal documents**
- All secret-like config goes through the `.env` file, which is excluded by `.gitignore`
- `.env.example` is only a template; all values are `your_xxx_here` placeholders
- Processed documents are output to `output/` by default, which is also git-ignored
- If you accidentally commit a secret, rotate it immediately and clean the git history (see [GitHub's official guide](https://docs.github.com/code-security/secret-scanning/removing-sensitive-data-from-a-repository))

## License

MIT License. See [LICENSE](LICENSE).
