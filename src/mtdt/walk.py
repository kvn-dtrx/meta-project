#!/usr/bin/env python3

# ---
# description: >-
#   Shared checkout walk and catalog paths for meta-project mtdt deploys.
# ---

# ---

# --- Imports ---


import os
import sys
from collections.abc import Iterator
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("meta-project mtdt helpers require PyYAML") from exc

# --- Configuration ---

DEFAULT_META = Path.home() / "data/projects/permanent/meta-project"
DEFAULT_ANNEX = Path.home() / "data/projects/permanent/meta-project-annex"
MTDT_BASENAME = ".mtdt.yaml"

# --- Auxiliary Code ---


def meta_root() -> Path:
    raw = os.environ.get("META_PROJECT", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_META


def annex_root() -> Path:
    """Private hygiene annex that holds live catalogs."""
    raw = os.environ.get("META_PROJECT_ANNEX", "").strip()
    if raw:
        return Path(raw).expanduser()
    sibling = meta_root().parent / "meta-project-annex"
    if sibling.is_dir():
        return sibling
    return DEFAULT_ANNEX


def forks_catalog_path() -> Path:
    raw = os.environ.get("MTDT_FORKS_FILE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return annex_root() / "src/mtdt/forks.yaml"


def env_plans_catalog_path() -> Path:
    raw = os.environ.get("MTDT_ENV_PLANS_FILE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return annex_root() / "src/mtdt/env-plans.yaml"


def space_mounts_catalog_path() -> Path:
    raw = os.environ.get("MTDT_SPACE_MOUNTS_FILE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return annex_root() / "src/mtdt/space-mounts.yaml"


def load_yaml_mapping(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return data


def project_id_from_mtdt(path: Path) -> str | None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    pid = project.get("id")
    if pid is None:
        return None
    text = str(pid).strip()
    if not text or text == "null":
        return None
    return text


def iter_mtdt_files(roots: list[Path]) -> Iterator[Path]:
    for root in roots:
        root = root.expanduser()
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip heavy / irrelevant trees
            dirnames[:] = [
                d
                for d in dirnames
                if d not in {".git", "node_modules", ".venv", "venv", "__pycache__"}
            ]
            for name in filenames:
                if name.lower() == MTDT_BASENAME:
                    yield Path(dirpath) / name


def iter_checkouts(
    roots: list[Path],
) -> Iterator[tuple[Path, str]]:
    """Yield (project_dir, project.id) for each .mtdt.yaml with an id."""
    seen: set[Path] = set()
    for mtdt_path in iter_mtdt_files(roots):
        project_dir = mtdt_path.parent.resolve()
        if project_dir in seen:
            continue
        seen.add(project_dir)
        pid = project_id_from_mtdt(mtdt_path)
        if pid is None:
            continue
        yield project_dir, pid


def log_info(msg: str) -> None:
    print(f"[INFO]:  {msg}")


def log_debug(msg: str) -> None:
    print(f"[DEBUG]: {msg}")


def log_warn(msg: str) -> None:
    print(f"[WARN]:  {msg}", file=sys.stderr)


def log_error(msg: str) -> None:
    print(f"[ERROR]: {msg}", file=sys.stderr)
