"""Load and validate YAML rulesets, resolving ``extends`` chains.

Resolution order for any reference (top-level or an ``extends`` value):

1. Relative to the file that declared it (for ``extends`` only)
2. As given, relative to the current directory
3. A name inside ``rules_dir``
4. A built-in packaged ruleset

A ruleset may extend another; the chain is resolved depth-first and the
results merged field by field (see :func:`schema.merge_rulesets`). Cycles are
rejected rather than silently truncated, because a cycle means the author
misread their own configuration and any result would be arbitrary.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import Ruleset, merge_rulesets


def load_ruleset(path_or_name: str, rules_dir: str | None = None) -> Ruleset:
    """Load a ruleset and fully resolve its ``extends`` chain.

    Args:
        path_or_name: An existing file path or a bare name.
        rules_dir: Optional directory to resolve bare names against.

    Returns:
        A ruleset whose ``styles`` are complete and whose ``extends`` is None.

    Raises:
        FileNotFoundError: If no matching file is found.
        ValueError: If the YAML is invalid, fails schema validation, or the
            ``extends`` chain contains a cycle.
    """
    return _load_file(_resolve_ref(path_or_name, rules_dir, base_dir=None), rules_dir, ())


def list_rules(rules_dir: str | None = None) -> list[str]:
    """Return the names of available rulesets.

    Built-in names come first, then any ``*.yaml`` files in ``rules_dir``.
    """
    names: list[str] = []

    try:
        for res in resources.files(__package__).iterdir():
            if res.name.endswith(".yaml"):
                names.append(res.name.removesuffix(".yaml"))
    except (FileNotFoundError, ModuleNotFoundError):
        pass

    if rules_dir:
        directory = Path(rules_dir)
        if directory.is_dir():
            for path in sorted(directory.glob("*.yaml")):
                names.append(path.stem)

    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _load_file(path: Path, rules_dir: str | None, chain: tuple[Path, ...]) -> Ruleset:
    resolved = path.resolve()
    if resolved in chain:
        route = " -> ".join(p.name for p in (*chain, resolved))
        raise ValueError(f"Ruleset 'extends' cycle: {route}")

    ruleset = _parse(path)
    if not ruleset.extends:
        return ruleset

    base_path = _resolve_ref(ruleset.extends, rules_dir, base_dir=path.parent)
    base = _load_file(base_path, rules_dir, (*chain, resolved))
    return merge_rulesets(base, ruleset)


def _parse(path: Path) -> Ruleset:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError(f"Ruleset {path} must be a YAML mapping at the top level")
    try:
        return Ruleset.model_validate(raw)
    except ValidationError as e:
        raise ValueError(f"Ruleset {path} failed validation: {e}") from e


def _resolve_ref(ref: str, rules_dir: str | None, base_dir: Path | None) -> Path:
    """Turn a name or path into an existing file."""
    if base_dir is not None:
        relative = base_dir / ref
        if relative.is_file():
            return relative

    as_given = Path(ref)
    if as_given.is_file():
        return as_given

    if rules_dir:
        resolved = _resolve_by_name(ref, Path(rules_dir))
        if resolved is not None:
            return resolved

    builtin = _resolve_builtin_by_name(ref)
    if builtin is not None:
        return builtin

    where = f"relative to {base_dir}, " if base_dir else ""
    raise FileNotFoundError(
        f"Ruleset {ref!r} not found {where}in {rules_dir!r}, or as a built-in."
    )


def _resolve_by_name(name: str, rules_dir: Path) -> Path | None:
    stem = name.removesuffix(".yaml")
    for candidate in (rules_dir / f"{stem}.yaml", rules_dir / f"{stem}.yml"):
        if candidate.is_file():
            return candidate
    return None


def _resolve_builtin_by_name(name: str) -> Path | None:
    stem = name.removesuffix(".yaml")
    try:
        for res in resources.files(__package__).iterdir():
            if res.name == f"{stem}.yaml":
                with resources.as_file(res) as path:  # type: ignore[arg-type]
                    return Path(path)
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    return None
