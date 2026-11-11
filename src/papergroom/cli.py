"""Command-line entry.

The pipeline, wired together:

    parse → recover structure → label roles (AI) → resolve styles (ruleset) → write

The split matters. The AI only decides *what each paragraph is*; the ruleset
only decides *how it looks*. Neither layer does the other's job, which is
what makes the styling reproducible and testable.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from docx.opc.exceptions import PackageNotFoundError
from rich.console import Console

from .ai import label_document
from .ai.rules_draft import draft_rules, validate_draft
from .config import get_llm_config, get_processing_config
from .labels import LabelsError, export_labels, load_labels
from .parser import parse_document
from .report import write_report
from .rules.loader import list_rules, load_ruleset
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


class ProcessingError(RuntimeError):
    """A document could not be processed; the message is fit for the user."""


def _say(verbose: bool, message: str) -> None:
    if verbose:
        console.print(message)


def _process_one(
    input: Path,
    output: Path,
    *,
    rules: str | None,
    word_styles: bool,
    labels: Path | None,
    export_labels_path: Path | None,
    report: bool,
    debug_annotation: bool,
    dry_run: bool = False,
    verbose: bool = True,
) -> Path:
    """Process one document. Returns the output path.

    Raises :class:`ProcessingError` for anything the user can act on, so a
    batch run can report the file and keep going.
    """
    # 1. Parse.
    _say(verbose, f"[bold]Parsing[/bold] {input} ...")
    try:
        doc = parse_document(input)
    except (OSError, ValueError, PackageNotFoundError) as e:
        raise ProcessingError(f"cannot read {input}: {e}") from e
    _say(verbose, f"  {len(doc.paragraphs)} paragraphs parsed.")

    # 2. Recover structure. Documents drafted by an LLM and pasted into Word
    #    often carry a heading and its body — or several references — in a
    #    single paragraph. Split those before anything tries to style them.
    before = len(doc.paragraphs)
    structurize(doc)
    recovered = len(doc.paragraphs) - before
    if recovered:
        _say(
            verbose,
            f"[bold]Structure[/bold] {recovered} paragraph(s) recovered from merged text.",
        )
    else:
        _say(verbose, "[bold]Structure[/bold] no merged paragraphs found.")

    # 3. Load the ruleset that will decide every style.
    try:
        ruleset = load_ruleset(rules or DEFAULT_RULESET)
    except (FileNotFoundError, ValueError) as e:
        raise ProcessingError(f"cannot load ruleset: {e}") from e
    _say(verbose, f"[bold]Ruleset:[/bold] {ruleset.name}")

    # 3b. Human corrections, if any. Loaded after structure recovery because
    #     the indices refer to the recovered paragraphs.
    overrides = None
    if labels is not None:
        try:
            overrides = load_labels(labels, doc)
        except LabelsError as e:
            raise ProcessingError(f"cannot use labels: {e}") from e
        _say(verbose, f"[bold]Labels:[/bold] {len(overrides)} override(s) from {labels}")

    # 4. Label roles. The model decides what each paragraph is, and nothing
    #    about how it looks.
    _say(verbose, "[bold]Labeling[/bold] roles with AI ...")
    try:
        llm_config = get_llm_config()
    except ValueError as e:
        raise ProcessingError(str(e)) from e
    processing = get_processing_config(debug_annotation=debug_annotation)
    label_document(doc, llm_config, ruleset, processing, overrides=overrides)

    if export_labels_path is not None:
        written = export_labels(doc, export_labels_path)
        _say(verbose, f"  labels exported to {written}")

    labeled = sum(1 for p in doc.paragraphs if p.role.value != "unknown")
    _say(verbose, f"  {labeled}/{len(doc.paragraphs)} paragraphs labeled.")

    # 5. Resolve styles from the ruleset. Deterministic: the same document
    #    and ruleset always produce the same styles.
    resolve_styles(doc, ruleset)

    # 6. Write — unless this is a dry run, where the point is to inspect what
    #    would happen without committing to it. The report and label export
    #    still work, because they are how you inspect it.
    if dry_run:
        out_path = output.resolve()
        _say(verbose, f"[yellow]Dry run:[/yellow] would write {out_path}")
        styled = sum(
            1 for p in doc.paragraphs if p.resolved_style and not p.resolved_style.is_empty()
        )
        _say(verbose, f"  {styled}/{len(doc.paragraphs)} paragraphs would be restyled.")
    else:
        _say(verbose, f"[bold]Writing[/bold] {output} ...")
        out_path = write_document(doc, ruleset, output, word_styles=word_styles)

    if report:
        report_path = write_report(
            doc,
            ruleset,
            out_path.with_suffix(".report.html"),
            output_name=out_path.name,
            min_confidence=processing.min_confidence,
        )
        _say(verbose, f"  review report: {report_path}")

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
        _say(verbose, f"  annotations dumped to {dump_path}")

    if dry_run:
        _say(verbose, "[green]Done.[/green] Nothing written (dry run).")
    else:
        _say(verbose, f"[green]Done.[/green] Output: {out_path}")
    return out_path


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
    word_styles: bool = typer.Option(
        False,
        "--word-styles",
        help=(
            "Also map headings onto Word's built-in Heading styles, so the "
            "navigation pane and an automatic table of contents work. "
            "Off by default: direct formatting is more predictable."
        ),
    ),
    labels: Path = typer.Option(
        None,
        "--labels",
        help=(
            "JSON file of role overrides. Export one with --export-labels, edit "
            "the roles, pass it back. Overridden paragraphs skip the model."
        ),
    ),
    export_labels_path: Path = typer.Option(
        None,
        "--export-labels",
        help="Write an editable labels file for the processed document.",
    ),
    report: bool = typer.Option(
        False,
        "--report",
        help=(
            "Write an HTML review report next to the output: every paragraph's "
            "role, confidence and applied style, with uncertain ones highlighted."
        ),
    ),
    debug_annotation: bool = typer.Option(
        False,
        "--debug-annotation",
        help="Write a JSON dump of the roles and styles next to the output.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Run the whole pipeline but do not write the .docx. Useful with "
            "--report or --export-labels to inspect the result first."
        ),
    ),
) -> None:
    """Parse, recover structure, label roles, apply the ruleset, and export."""
    if output is None:
        output = input.parent / f"{input.stem}_formatted.docx"

    try:
        _process_one(
            input,
            output,
            rules=rules,
            word_styles=word_styles,
            labels=labels,
            export_labels_path=export_labels_path,
            report=report,
            debug_annotation=debug_annotation,
            dry_run=dry_run,
        )
    except ProcessingError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e


@app.command("process-dir")
def process_dir(
    directory: Path = typer.Argument(
        ..., exists=True, file_okay=False, help="Directory of .docx files."
    ),
    output_dir: Path = typer.Option(
        None,
        "-o",
        "--output-dir",
        help="Where to write results. Defaults to <directory>/formatted.",
    ),
    rules: str = typer.Option(
        None, "-r", "--rules", help="Ruleset path or built-in name."
    ),
    recursive: bool = typer.Option(
        False, "--recursive", help="Include subdirectories."
    ),
    word_styles: bool = typer.Option(False, "--word-styles"),
    report: bool = typer.Option(False, "--report"),
    debug_annotation: bool = typer.Option(False, "--debug-annotation"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Do not write the .docx files; reports still work."
    ),
) -> None:
    """Process every .docx in a directory, continuing past failures.

    Per-document labels and label export are not available here: their
    indices refer to one document.
    """
    out_dir = output_dir or directory / "formatted"
    if out_dir.resolve() == directory.resolve():
        console.print("[red]Output directory must differ from the input directory.[/red]")
        raise typer.Exit(code=1)

    candidates = directory.rglob("*.docx") if recursive else directory.glob("*.docx")
    files = sorted(
        f
        for f in candidates
        # Word leaves ~$ lock files next to open documents.
        if not f.name.startswith("~$")
        and out_dir.resolve() not in f.resolve().parents
    )
    if not files:
        console.print("No .docx files found.")
        raise typer.Exit(code=1)

    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[tuple[Path, Exception]] = []

    for source in files:
        target = (
            out_dir / source.relative_to(directory) if recursive else out_dir / source.name
        )
        try:
            _process_one(
                source,
                target,
                rules=rules,
                word_styles=word_styles,
                labels=None,
                export_labels_path=None,
                report=report,
                debug_annotation=debug_annotation,
                dry_run=dry_run,
                verbose=False,
            )
            console.print(f"[green]ok[/green]   {source.name}")
        except Exception as e:  # keep going: one bad file must not stop the run
            failures.append((source, e))
            console.print(f"[red]fail[/red] {source.name}: {e}")

    verb = "checked" if dry_run else "processed"
    console.print(
        f"\n{len(files) - len(failures)}/{len(files)} {verb}."
        + ("" if dry_run else f" Output: {out_dir}")
    )
    if failures:
        raise typer.Exit(code=1)


@app.command("draft-rules")
def draft_rules_command(
    description: str = typer.Argument(
        ..., help="Formatting requirements, in natural language."
    ),
    output: Path = typer.Option(
        ..., "-o", "--output", help="Where to write the YAML draft."
    ),
    base: str = typer.Option(
        "standard_thesis", "--base", help="Ruleset the draft should extend."
    ),
) -> None:
    """Draft a ruleset YAML from a description. Review it before using it."""
    llm_config = get_llm_config()
    console.print(f"[bold]Drafting[/bold] a ruleset extending {base} ...")

    try:
        text = draft_rules(description, llm_config, base)
    except Exception as e:  # network or provider error
        console.print(f"[red]Draft failed:[/red] {e}")
        raise typer.Exit(code=1) from e

    try:
        validate_draft(text)  # schema only; extends is resolved below
    except ValueError as e:
        console.print("[red]The model returned an invalid ruleset:[/red]")
        console.print(text)
        console.print(f"\n{e}")
        raise typer.Exit(code=1) from e

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    console.print(f"Wrote [bold]{output}[/bold]")

    # Warn on the *resolved* ruleset: the draft only lists overrides, so
    # checking it directly would claim every inherited role is missing.
    try:
        resolved = load_ruleset(str(output))
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Written, but the draft does not load:[/red] {e}")
        raise typer.Exit(code=1) from e

    for warning in check_ruleset(resolved):
        console.print(f"[yellow]warning:[/yellow] {warning}")

    console.print(
        "[yellow]This is a draft.[/yellow] Review it, then run "
        f"`papergroom validate-rules {output}`."
    )


@app.command("list-rules")
def list_rules_command(
    rules_dir: str = typer.Option(
        None,
        "--rules-dir",
        help="Directory of additional .yaml rulesets to include.",
    ),
) -> None:
    """List the rulesets available to --rules."""
    names = list_rules(rules_dir)
    if not names:
        console.print("No rulesets found.")
        return
    for name in names:
        console.print(name)


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
