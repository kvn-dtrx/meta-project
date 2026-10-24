#!/usr/bin/env python3

# ---
# description: >-
#   Shared mtdt consumers and private catalogue paths for meta-project
# ---

# ---

# --- Imports ---


import os
import shutil
import subprocess
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
SKIP_DIRS = {".venv", "__pycache__", "node_modules", "venv"}

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


def config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".config"


def _catalog_path(
    variable: str,
    compatibility_variable: str,
    xdg_name: str,
    annex_name: str,
    legacy_name: str,
) -> Path:
    raw = os.environ.get(variable, "").strip()
    if not raw:
        raw = os.environ.get(compatibility_variable, "").strip()
    if raw:
        return Path(raw).expanduser()
    candidates = (
        config_home() / "meta-project" / xdg_name,
        annex_root() / "src/wire/meta-project/config" / annex_name,
        annex_root() / "src/mtdt" / legacy_name,
    )
    return next((path for path in candidates if path.is_file()), candidates[0])


def env_plans_catalog_path() -> Path:
    return _catalog_path(
        "META_PROJECT_ENVS_FILE",
        "MTDT_ENV_PLANS_FILE",
        "envs.yaml",
        "envs.yaml",
        "env-plans.yaml",
    )


def space_mounts_catalog_path() -> Path:
    return _catalog_path(
        "META_PROJECT_MOUNTS_FILE",
        "MTDT_SPACE_MOUNTS_FILE",
        "mounts.yaml",
        "mounts.yaml",
        "space-mounts.yaml",
    )


def load_yaml_mapping(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return data


def _mtdt_tool(variable: str, name: str) -> str:
    override = os.environ.get(variable, "").strip()
    if override:
        return str(Path(override).expanduser())
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"{name} not found; install the mtdt repository")


def project_id_from_mtdt(path: Path) -> str | None:
    command = _mtdt_tool("MTDT_PROJECT_ID_COMMAND", "mtdt-project-id")
    proc = subprocess.run(
        [command, str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def load_effective_metadata(project_dir: Path) -> dict:
    """Load metadata through mtdt so local forge overlays take precedence."""
    command = _mtdt_tool("MTDT_RESOLVE_COMMAND", "resolve-mtdt")
    metadata_path = project_dir / ".mtdt.yaml"
    proc = subprocess.run(
        [command, str(metadata_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit status {proc.returncode}"
        raise RuntimeError(f"resolve-mtdt failed for {project_dir}: {detail}")
    try:
        data = yaml.safe_load(proc.stdout)
    except yaml.YAMLError as exc:
        raise RuntimeError(
            f"resolve-mtdt returned invalid YAML for {project_dir}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"resolve-mtdt returned no mapping for {project_dir}")
    return data


def iter_git_checkouts(roots: list[Path]) -> Iterator[Path]:
    """Yield Git checkout roots without depending on project metadata."""
    seen: set[Path] = set()
    for root in roots:
        root = root.expanduser()
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            directory = Path(dirpath)
            if ".git" in dirnames or ".git" in filenames:
                resolved = directory.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield resolved
            dirnames[:] = sorted(
                name for name in dirnames if name != ".git" and name not in SKIP_DIRS
            )


def iter_checkouts(
    roots: list[Path],
) -> Iterator[tuple[Path, str]]:
    """Yield projects through mtdt's stable discovery interface."""
    command = _mtdt_tool("MTDT_LIST_PROJECTS_COMMAND", "mtdt-list-projects")
    proc = subprocess.run(
        [command, *(str(root) for root in roots)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit status {proc.returncode}"
        raise RuntimeError(f"mtdt-list-projects failed: {detail}")
    for line in proc.stdout.splitlines():
        project_id, separator, directory = line.partition("\t")
        if not separator or not project_id or not directory:
            raise RuntimeError(f"invalid mtdt-list-projects record: {line!r}")
        yield Path(directory), project_id


def log_info(msg: str) -> None:
    print(f"[INFO]:  {msg}")


def log_debug(msg: str) -> None:
    print(f"[DEBUG]: {msg}")


def log_warn(msg: str) -> None:
    print(f"[WARN]:  {msg}", file=sys.stderr)


def log_error(msg: str) -> None:
    print(f"[ERROR]: {msg}", file=sys.stderr)
