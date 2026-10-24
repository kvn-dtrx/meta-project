#!/usr/bin/env python3

# ---
# description: >-
#   Tests cross-repository Just recipe and Make target discovery
# ---

# ---

# --- Imports ---

from pathlib import Path

from meta_project.recipes import matches, parse_just_dump, parse_makefile, render

# --- Main Code ---


def test_parse_just_dump_omits_private_and_default_recipes() -> None:
    repository = Path("/projects/example")
    data = {
        "recipes": {
            "default": {
                "name": "default",
                "namepath": "default",
                "private": False,
                "parameters": [],
                "doc": "Lists recipes",
            },
            "build": {
                "name": "build",
                "namepath": "build",
                "private": False,
                "parameters": [
                    {"name": "query", "kind": "singular", "default": None},
                    {"name": "mode", "kind": "singular", "default": ""},
                ],
                "doc": "Builds one note",
            },
            "_helper": {
                "name": "_helper",
                "namepath": "_helper",
                "private": True,
                "parameters": [],
                "doc": None,
            },
        }
    }

    recipes = parse_just_dump(repository, data)

    assert [recipe.signature for recipe in recipes] == ["build query [mode='']"]
    assert recipes[0].description == "Builds one note"


def test_parse_makefile_reads_only_documented_literal_targets() -> None:
    repository = Path("/projects/example")
    text = """\
.PHONY: install internal
install: prepare ## Installs user commands
_internal: ## Internal helper
pattern-%: ## Pattern target
undocumented:
"""

    recipes = parse_makefile(repository, text)

    assert [(recipe.name, recipe.description) for recipe in recipes] == [
        ("install", "Installs user commands")
    ]


def test_filter_and_render_group_by_repository_and_tool() -> None:
    repository = Path("/projects/notes")
    just_recipe = parse_just_dump(
        repository,
        {
            "recipes": {
                "export": {
                    "name": "export",
                    "namepath": "export",
                    "private": False,
                    "parameters": [],
                    "doc": "Exports notes",
                }
            }
        },
    )[0]
    make_recipe = parse_makefile(repository, "install: ## Installs note tooling\n")[0]

    assert matches(just_recipe, ["export", "notes"], "not")
    assert not matches(just_recipe, ["backup"], "")
    assert render([just_recipe, make_recipe]) == (
        "notes\n"
        "  just\n"
        "    export — Exports notes\n"
        "  make\n"
        "    install — Installs note tooling\n"
    )
