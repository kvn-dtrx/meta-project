#!/usr/bin/env python3

# ---
# description: >-
#   Discovers documented Just recipes and Make targets across project checkouts
# ---

# ---

# --- Imports ---


import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# --- Configuration ---

JUSTFILE_NAMES = ("justfile", "Justfile", ".justfile")
MAKEFILE_NAMES = ("Makefile", "makefile", "GNUmakefile")
MAKE_TARGET = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*")

# --- Auxiliary Code ---


@dataclass(frozen=True, order=True)
class Recipe:
    repository: str
    tool: str
    name: str
    signature: str
    description: str
    path: Path


def first_file(directory: Path, names: tuple[str, ...]) -> Path | None:
    return next(
        (directory / name for name in names if (directory / name).is_file()), None
    )


def format_parameter(parameter: dict) -> str:
    name = str(parameter.get("name", "ARG"))
    kind = parameter.get("kind")
    if kind == "star":
        return f"*{name}"
    if kind == "plus":
        return f"+{name}"
    default = parameter.get("default")
    if default is not None:
        return f"[{name}={default!r}]"
    return name


def parse_just_dump(repository: Path, data: dict) -> list[Recipe]:
    recipes: list[Recipe] = []
    raw_recipes = data.get("recipes", {})
    if not isinstance(raw_recipes, dict):
        raise ValueError("Just dump has no recipes mapping")
    for raw in raw_recipes.values():
        if not isinstance(raw, dict) or raw.get("private"):
            continue
        name = str(raw.get("namepath") or raw.get("name") or "")
        if not name or name == "default" or name.rsplit("::", 1)[-1].startswith("_"):
            continue
        parameters = raw.get("parameters", [])
        arguments = " ".join(
            format_parameter(parameter)
            for parameter in parameters
            if isinstance(parameter, dict)
        )
        signature = f"{name} {arguments}".rstrip()
        description = str(raw.get("doc") or "").strip()
        recipes.append(
            Recipe(
                repository=repository.name,
                tool="just",
                name=name,
                signature=signature,
                description=description,
                path=repository,
            )
        )
    return recipes


def read_just_recipes(
    repository: Path, justfile: Path, just_command: str
) -> list[Recipe]:
    process = subprocess.run(
        [
            just_command,
            "--justfile",
            str(justfile),
            "--working-directory",
            str(repository),
            "--dump",
            "--dump-format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or f"exit status {process.returncode}"
        raise RuntimeError(detail)
    try:
        data = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Just returned malformed JSON") from error
    if not isinstance(data, dict):
        raise RuntimeError("Just returned no JSON object")
    return parse_just_dump(repository, data)


def parse_makefile(repository: Path, text: str) -> list[Recipe]:
    recipes: list[Recipe] = []
    for line in text.splitlines():
        definition, marker, description = line.partition("##")
        if not marker or ":" not in definition:
            continue
        targets, _separator, _prerequisites = definition.partition(":")
        for name in targets.split():
            if (
                not MAKE_TARGET.fullmatch(name)
                or name.startswith((".", "_"))
                or "%" in name
            ):
                continue
            recipes.append(
                Recipe(
                    repository=repository.name,
                    tool="make",
                    name=name,
                    signature=name,
                    description=description.strip(),
                    path=repository,
                )
            )
    return recipes


def read_make_recipes(repository: Path, makefile: Path) -> list[Recipe]:
    return parse_makefile(repository, makefile.read_text(encoding="utf-8"))


def matches(recipe: Recipe, queries: list[str], repository_query: str) -> bool:
    if repository_query.casefold() not in recipe.repository.casefold():
        return False
    haystack = " ".join(
        (
            recipe.repository,
            recipe.tool,
            recipe.signature,
            recipe.description,
        )
    ).casefold()
    return all(query.casefold() in haystack for query in queries)


def render(recipes: list[Recipe], show_paths: bool = False) -> str:
    lines: list[str] = []
    repositories = sorted({recipe.repository for recipe in recipes})
    for repository in repositories:
        repository_recipes = [
            recipe for recipe in recipes if recipe.repository == repository
        ]
        label = repository
        if show_paths:
            label += f" ({repository_recipes[0].path})"
        lines.append(label)
        for tool in ("just", "make"):
            tool_recipes = sorted(
                (recipe for recipe in repository_recipes if recipe.tool == tool),
                key=lambda recipe: recipe.name,
            )
            if not tool_recipes:
                continue
            lines.append(f"  {tool}")
            for recipe in tool_recipes:
                suffix = f" — {recipe.description}" if recipe.description else ""
                lines.append(f"    {recipe.signature}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + ("\n" if lines else "")
