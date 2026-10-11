"""Command-line entry: `papergroom process`.

Wires the layers together:
  parse → AI label (reads rules + decides styles) → apply → write
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from .ai import label_document
from .config import get_llm_config, get_processing_config
from .parser import parse_document
from .rules.rules_text import resolve_rules_text
from .writer import write_document

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
            "Path to a formatting rules text file (.txt/.md). "
            "If omitted, the built-in standard thesis rules are used."
        ),
    ),
    debug_annotation: bool = typer.Option(
        False,
        "--debug-annotation",
        help="Write a JSON dump of AI labels + styles next to the output.",
    ),
) -> None:
    """Parse, label with AI (reading formatting rules), apply styles, and export."""
    if output is None:
        output = input.parent / f"{input.stem}_formatted.docx"

    # 1. Parse.
    console.print(f"[bold]Parsing[/bold] {input} ...")
    doc = parse_document(input)
    console.print(f"  {len(doc.paragraphs)} paragraphs parsed.")

    # 2. Load formatting rules text.
    rules_text, rules_source = resolve_rules_text(rules)
    console.print(f"[bold]Rules:[/bold] {rules_source}")

    # 3. Label with AI — the AI reads the rules and decides per-paragraph styles.
    console.print("[bold]Labeling[/bold] paragraphs with AI ...")
    llm_config = get_llm_config()
    processing = get_processing_config(debug_annotation=debug_annotation)
    annotation = label_document(doc, llm_config, rules_text, processing)

    labeled = sum(1 for p in doc.paragraphs if p.role.value != "unknown")
    console.print(f"  {labeled}/{len(doc.paragraphs)} paragraphs labeled.")

    # 4. Apply + write. Styles come from para.resolved_style (set by the AI).
    console.print(f"[bold]Writing[/bold] {output} ...")
    out_path = write_document(doc, None, output)

    # Optional debug dump.
    if debug_annotation:
        dump_path = out_path.with_suffix(".annotations.json")
        dump_path.write_text(
            json.dumps(
                {
                    "source": doc.source_path,
                    "rules": rules_source,
                    "paragraphs": [
                        {
                            "index": p.index,
                            "role": p.role.value,
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


if __name__ == "__main__":
    app()
