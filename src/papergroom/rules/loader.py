"""Load and validate YAML rulesets.

Rulesets are searched in this order:

1. An explicit path passed to :func:`load_ruleset` (absolute or relative
   to CWD). Used by ``--rules`` on the CLI.
2. A name resolved against ``--rules-dir`` (e.g. ``my_thesis``).
3. The built-in package rulesets shipped under ``papergroom/rules/*.yaml``.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import Ruleset

def load_ruleset(path_or_name: str, rules_dir: str | None = None) -> Ruleset:
    """Load a ruleset from a path, a name in ``rules_dir``, or built-ins.

    Args:
        path_or_name: Either an existing file path (``foo/bar.yaml``) or a
            bare name (``standard_thesis``). Names are resolved against
            ``rules_dir`` first, then built-in package rulesets.
        rules_dir: Optional directory to resolve bare names against.

    Returns:
        A validated :class:`Ruleset`.

    Raises:
        FileNotFoundError: If no matching file is found.
        ValueError: If the YAML is invalid or fails schema validation.
    """
    # 1. Explicit path
    candidate = Path(path_or_name)
    if candidate.exists() and candidate.is_file():
        return _load_from_file(candidate)

    # 2. Bare name against rules_dir
    if rules_dir:
        resolved = _resolve_by_name(path_or_name, Path(rules_dir))
        if resolved is not None:
            return _load_from_file(resolved)

    # 3. Built-in package ruleset by name
    builtin = _resolve_builtin_by_name(path_or_name)
    if builtin is not None:
        return _load_from_file(builtin)

    raise FileNotFoundError(
        f"Ruleset {path_or_name!r} not found as path, "
        f"in rules_dir={rules_dir!r}, or as a built-in ruleset."
    )


def list_rules(rules_dir: str | None = None) -> list[str]:
    """Return the names of available rulesets.

    Built-in names come first, then any ``*.yaml`` files in ``rules_dir``.
    Names are returned without the ``.yaml`` extension.
    """
    names: list[str] = []

    # Built-ins (shipped inside the papergroom.rules package directory)
    try:
        for res in resources.files(__package__).iterdir():
            if res.name.endswith(".yaml"):
                names.append(res.name.removesuffix(".yaml"))
    except (FileNotFoundError, ModuleNotFoundError):
        pass

    # User dir
    if rules_dir:
        d = Path(rules_dir)
        if d.is_dir():
            for p in sorted(d.glob("*.yaml")):
                names.append(p.stem)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    return unique


def _load_from_file(path: Path) -> Ruleset:
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


def _resolve_by_name(name: str, rules_dir: Path) -> Path | None:
    # Allow both "standard_thesis" and "standard_thesis.yaml"
    stem = name.removesuffix(".yaml")
    for candidate in (rules_dir / f"{stem}.yaml", rules_dir / f"{stem}.yml"):
        if candidate.is_file():
            return candidate
    return None


def _resolve_builtin_by_name(name: str) -> Path | None:
    """Find a built-in ruleset by name.

    Uses importlib.resources to locate files packaged under
    ``papergroom/rules/``. Returns a concrete Path on disk if found.
    """
    stem = name.removesuffix(".yaml")
    try:
        pkg_dir = resources.files(__package__)
        for res in pkg_dir.iterdir():
            if res.name == f"{stem}.yaml":
                # importlib.resources returns Traversable; for on-disk packages
                # we can resolve to a Path via as_file().
                with resources.as_file(res) as p:  # type: ignore[arg-type]
                    return Path(p)
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    return None
