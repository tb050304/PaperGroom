"""Command-line entry: `papergroom process`.

Wires the layers together:

    parse → recover structure → label roles (AI) → resolve styles (ruleset) → write

The split matters. The AI only decides *what each paragraph is*; the ruleset
only decides *how it looks*. Neither layer does the other's job, which is
what makes the styling reproducible and testable.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from .ai import label_document
from .config import get_llm_config, get_processing_config
from .parser import parse_document
from .rules.loader import load_ruleset
from .rules.resolve import resolve_styles
from .rules.validate import validate_ruleset as check_ruleset
from .structure import structurize
from .writer import write_document

DEFAULT_RULESET = "standard_thesis"

app = typer.Typer(
    name="papergroom",
    help="AI-powered Word document formatter.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def process(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, help="Input .docx path"),
    output: Path = typer.Option(
        None,
        "-o",
        "--output",
        help="Output .docx path. Defaults to <input>_formatted.docx next to the input.",
    ),
    rules: str = typer.Option(
        None,
        "-r",
        "--rules",
        help=(
            "Ruleset: a path to a .yaml file, or the name of a built-in. "
            f"Defaults to the built-in '{DEFAULT_RULESET}'."
        ),
    ),
    debug_annotation: bool = typer.Option(
        False,
        "--debug-annotation",
        help="Write a JSON dump of the roles and styles next to the output.",
    ),
) -> None:
    """Parse, recover structure, label roles, apply the ruleset, and export."""
    if output is None:
        output = input.parent / f"{input.stem}_formatted.docx"

    # 1. Parse.
    console.print(f"[bold]Parsing[/bold] {input} ...")
    doc = parse_document(input)
    console.print(f"  {len(doc.paragraphs)} paragraphs parsed.")

    # 2. Recover structure. Documents drafted by an LLM and pasted into Word
    #    often carry a heading and its body — or several references — in a
    #    single paragraph. Split those before anything tries to style them.
    before = len(doc.paragraphs)
    structurize(doc)
    recovered = len(doc.paragraphs) - before
    if recovered:
        console.print(
            f"[bold]Structure[/bold] {recovered} paragraph(s) recovered from merged text."
        )
    else:
        console.print("[bold]Structure[/bold] no merged paragraphs found.")

    # 3. Load the ruleset that will decide every style.
    try:
        ruleset = load_ruleset(rules or DEFAULT_RULESET)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Cannot load ruleset:[/red] {e}")
        raise typer.Exit(code=1) from e
    console.print(f"[bold]Ruleset:[/bold] {ruleset.name}")

    # 4. Label roles. The model decides what each paragraph is, and nothing
    #    about how it looks.
    console.print("[bold]Labeling[/bold] roles with AI ...")
    llm_config = get_llm_config()
    processing = get_processing_config(debug_annotation=debug_annotation)
    label_document(doc, llm_config, ruleset, processing)

    labeled = sum(1 for p in doc.paragraphs if p.role.value != "unknown")
    console.print(f"  {labeled}/{len(doc.paragraphs)} paragraphs labeled.")

    # 5. Resolve styles from the ruleset. Deterministic: the same document
    #    and ruleset always produce the same styles.
    resolve_styles(doc, ruleset)

    # 6. Write.
    console.print(f"[bold]Writing[/bold] {output} ...")
    out_path = write_document(doc, None, output)

    if debug_annotation:
        dump_path = out_path.with_suffix(".annotations.json")
        dump_path.write_text(
            json.dumps(
                {
                    "source": doc.source_path,
                    "ruleset": ruleset.name,
                    "paragraphs": [
                        {
                            "index": p.index,
                            "source_index": p.source_index,
                            "role": p.role.value,
                            "role_hint": p.role_hint.value if p.role_hint else None,
                            "confidence": p.confidence,
                            "text_preview": p.text[:80],
                            "style": (
                                p.resolved_style.model_dump(exclude_none=True)
                                if p.resolved_style
                                else None
                            ),
                        }
                        for p in doc.paragraphs
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        console.print(f"  annotations dumped to {dump_path}")

    console.print(f"[green]Done.[/green] Output: {out_path}")


@app.command("validate-rules")
def validate_rules_command(
    rules: str = typer.Argument(..., help="Ruleset path or built-in name."),
) -> None:
    """Load a ruleset (resolving 'extends') and report anything suspicious."""
    try:
        ruleset = load_ruleset(rules)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Invalid ruleset:[/red] {e}")
        raise typer.Exit(code=1) from e

    console.print(f"[bold]{ruleset.name}[/bold]: {len(ruleset.styles)} role styles")
    warnings = check_ruleset(ruleset)
    for warning in warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")
    if not warnings:
        console.print("[green]OK[/green]")


if __name__ == "__main__":
    app()
