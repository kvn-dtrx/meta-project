#!/usr/bin/env python3

# ---
# description: >-
#   Lists and searches documented Just recipes and Make targets across repositories
# ---

# ---

# --- Imports ---


import argparse
import os
import shutil
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from meta_project.recipes import (  # noqa: E402
    JUSTFILE_NAMES,
    MAKEFILE_NAMES,
    first_file,
    matches,
    read_just_recipes,
    read_make_recipes,
    render,
)
from meta_project.walk import iter_checkouts, log_warn  # noqa: E402

# --- Auxiliary Code ---


def parse_arguments(arguments: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List and search repository Just recipes and Make targets."
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="terms which must occur in the repository, command, or description",
    )
    parser.add_argument(
        "--repo",
        default="",
        metavar="TEXT",
        help="restrict repository names by case-insensitive substring",
    )
    tools = parser.add_mutually_exclusive_group()
    tools.add_argument("--just", action="store_true", help="show only Just recipes")
    tools.add_argument("--make", action="store_true", help="show only Make targets")
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        metavar="PATH",
        help="project tree to scan; may be repeated",
    )
    parser.add_argument(
        "--paths", action="store_true", help="show each repository's absolute path"
    )
    return parser.parse_args(arguments)


def default_root() -> Path:
    raw = os.environ.get("META_PROJECTS_ROOT", "").strip()
    if not raw:
        raw = os.environ.get("MTDT_PROJECTS_ROOT", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / "data/projects"


# --- Main Code ---


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(arguments)
    roots = options.root or [default_root()]
    just_command = shutil.which("just")
    recipes = []
    for repository, _project_id in iter_checkouts(roots):
        if not options.make:
            justfile = first_file(repository, JUSTFILE_NAMES)
            if justfile is not None:
                if just_command is None:
                    log_warn(f"Skipping {repository}: just is not installed")
                else:
                    try:
                        recipes.extend(
                            read_just_recipes(repository, justfile, just_command)
                        )
                    except RuntimeError as error:
                        log_warn(f"Skipping Just recipes in {repository}: {error}")
        if not options.just:
            makefile = first_file(repository, MAKEFILE_NAMES)
            if makefile is not None:
                recipes.extend(read_make_recipes(repository, makefile))

    selected = [
        recipe for recipe in recipes if matches(recipe, options.query, options.repo)
    ]
    if not selected:
        print("No matching documented recipes.", file=sys.stderr)
        return 1
    print(render(selected, options.paths), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
