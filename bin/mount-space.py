#!/usr/bin/env python3

# ---
# description: >-
#   Apply meta-project-annex space-mounts.yaml: ensure <space>/mnt/.gitkeep and
#   link mnt/<link> → the catalogued data-stem checkout. Symlinks are local
#   (gitignore mnt/*; force-add .gitkeep).
# ---

# ---

# --- Imports ---


import argparse
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from mtdt.walk import (  # noqa: E402
    iter_checkouts,
    load_yaml_mapping,
    log_error,
    log_info,
    log_warn,
    project_id_from_mtdt,
    space_mounts_catalog_path,
)

# --- Configuration ---

DEFAULT_PROJECTS = Path.home() / "data/projects"
STAGES = ("permanent", "staged", "running", "archive", "review")

# --- Auxiliary Code ---


def projects_root() -> Path:
    raw = os.environ.get("MTDT_PROJECTS_ROOT", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_PROJECTS


def find_named_dir(name: str, root: Path) -> Path | None:
    found: Path | None = None
    for stage in STAGES:
        candidate = root / stage / name
        if candidate.is_dir():
            if found is not None and found.resolve() != candidate.resolve():
                raise RuntimeError(
                    f"multiple checkouts for {name}:\n  {found}\n  {candidate}"
                )
            found = candidate
    if found is not None:
        return found.resolve()
    if not root.is_dir():
        return None
    for dirpath, dirnames, _filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in {".git", "node_modules", ".venv", "venv", "__pycache__"}
        ]
        base = Path(dirpath).name
        if base != name:
            continue
        candidate = Path(dirpath)
        if found is not None and found.resolve() != candidate.resolve():
            raise RuntimeError(
                f"multiple checkouts for {name}:\n  {found}\n  {candidate}"
            )
        found = candidate
    return found.resolve() if found is not None else None


def find_by_project_id(pid: str, root: Path) -> Path | None:
    for project_dir, found_id in iter_checkouts([root]):
        if found_id == pid:
            return project_dir
    return None


def resolve_data_dir(entry: dict, root: Path) -> Path:
    data = entry.get("data")
    if isinstance(data, str):
        data = {"stem": data}
    if not isinstance(data, dict):
        raise ValueError("mount entry needs data: mapping (or stem string)")

    data_id = data.get("id")
    stem = data.get("stem")
    if data_id:
        by_id = find_by_project_id(str(data_id), root)
        if by_id is not None:
            return by_id
    if stem:
        by_name = find_named_dir(str(stem), root)
        if by_name is not None:
            return by_name
        raise FileNotFoundError(
            f"data checkout not found for stem={stem!r} under {root}"
        )
    raise ValueError("data: needs id: and/or stem:")


def ensure_gitkeep(mnt: Path, check_only: bool) -> bool:
    """Return True if ok / written; False if missing under --check."""
    keep = mnt / ".gitkeep"
    if check_only:
        return mnt.is_dir() and keep.is_file()
    mnt.mkdir(parents=True, exist_ok=True)
    if not keep.is_file():
        keep.write_text("", encoding="utf-8")
        log_info(f"wrote {keep}")
    return True


def link_target(path: Path) -> Path | None:
    if path.is_symlink():
        return path.resolve()
    if path.exists():
        raise RuntimeError(f"{path} exists and is not a symlink")
    return None


def expand_link_specs(entry: dict) -> list[dict]:
    """Normalise a catalog entry to a list of {link, data} specs."""
    links = entry.get("links")
    if links is not None:
        if not isinstance(links, list) or not links:
            raise ValueError("links: must be a non-empty list")
        out: list[dict] = []
        for item in links:
            if not isinstance(item, dict):
                raise ValueError("links: entries must be mappings")
            link = item.get("link")
            if not link:
                raise ValueError("links: each entry needs link:")
            data = item.get("data")
            if data is None:
                raise ValueError(f"links: {link!r} needs data:")
            out.append({"link": str(link), "data": data})
        return out

    if "data" in entry:
        return [
            {
                "link": str(entry.get("link") or "data"),
                "data": entry.get("data"),
            }
        ]

    raise ValueError("mount entry needs data: or links:")


def apply_link(
    space_dir: Path,
    link_name: str,
    data_spec: object,
    *,
    check_only: bool,
    data_override: Path | None,
    root: Path,
) -> int:
    """Return 0 ok, 1 drift/error for one mnt/<link>."""
    mnt = space_dir / "mnt"
    link_path = mnt / link_name

    if not ensure_gitkeep(mnt, check_only):
        log_warn(f"MISSING {mnt}/.gitkeep")
        return 1

    try:
        if data_override is not None:
            data_dir = data_override.resolve()
        else:
            data_dir = resolve_data_dir({"data": data_spec}, root)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        log_error(f"{space_dir}: {exc}")
        return 1

    if not data_dir.is_dir():
        log_error(f"{space_dir}: data dir missing: {data_dir}")
        return 1

    try:
        cur = link_target(link_path)
    except RuntimeError as exc:
        log_error(str(exc))
        return 1

    if cur == data_dir:
        log_info(f"ok {link_path} → {data_dir}")
        return 0

    if check_only:
        if cur is None:
            log_warn(f"MISSING {link_path} → {data_dir}")
        else:
            log_warn(f"DIVERGE {link_path}: {cur} → want {data_dir}")
        return 1

    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()
    link_path.symlink_to(data_dir)
    log_info(f"linked {link_path} → {data_dir}")
    return 0


def apply_entry(
    space_dir: Path,
    entry: dict,
    *,
    check_only: bool,
    data_override: Path | None,
    root: Path,
) -> int:
    """Apply all links for one space catalog entry. Return drift count."""
    try:
        specs = expand_link_specs(entry)
    except ValueError as exc:
        log_error(f"{space_dir}: {exc}")
        return 1

    if data_override is not None and len(specs) != 1:
        log_error(f"{space_dir}: --data only works with a single-link mount entry")
        return 1

    drift = 0
    for spec in specs:
        drift += apply_link(
            space_dir,
            spec["link"],
            spec["data"],
            check_only=check_only,
            data_override=data_override,
            root=root,
        )
    return drift


def load_mounts() -> dict:
    path = space_mounts_catalog_path()
    try:
        catalog = load_yaml_mapping(path)
    except FileNotFoundError:
        log_error(f"space-mounts catalog not found: {path}")
        raise SystemExit(1) from None
    mounts = catalog.get("mounts")
    if not isinstance(mounts, dict):
        log_error(f"{path}: missing mounts: mapping")
        raise SystemExit(1)
    return mounts


def resolve_space_arg(target: str | None, root: Path) -> Path:
    if target is None:
        return Path.cwd().resolve()
    p = Path(target).expanduser()
    if p.is_dir():
        return p.resolve()
    if target.endswith("-space"):
        found = find_named_dir(target, root)
    else:
        found = find_named_dir(f"{target}-space", root)
    if found is None:
        raise FileNotFoundError(f"space checkout not found for {target!r}")
    return found


# --- Main Code ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Link space mnt/<link> from meta-project-annex space-mounts.yaml "
            "(by space project.id)."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift only (exit 1 if any)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="apply every catalog entry (scan MTDT_PROJECTS_ROOT)",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="override data checkout (single-space mode only)",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="space dir, stem, or stem-space (default: .)",
    )
    args = parser.parse_args(argv)

    if args.all and args.data is not None:
        log_error("--data cannot be combined with --all")
        return 2
    if args.all and args.target is not None:
        log_error("positional target cannot be combined with --all")
        return 2

    mounts = load_mounts()
    root = projects_root()
    drift = 0

    if args.all:
        id_to_dir = {pid: path for path, pid in iter_checkouts([root])}
        for space_id, entry in mounts.items():
            if not isinstance(entry, dict):
                log_error(f"catalog {space_id}: entry must be a mapping")
                drift += 1
                continue
            space_dir = id_to_dir.get(str(space_id))
            if space_dir is None:
                log_warn(f"skip {space_id}: space checkout not found")
                continue
            drift += apply_entry(
                space_dir,
                entry,
                check_only=args.check,
                data_override=None,
                root=root,
            )
        log_info(f"catalog={space_mounts_catalog_path()}")
        return 1 if drift else 0

    try:
        space_dir = resolve_space_arg(args.target, root)
    except FileNotFoundError as exc:
        log_error(str(exc))
        return 1

    mtdt = space_dir / ".mtdt.yaml"
    if not mtdt.is_file():
        log_error(f"{space_dir}: missing .mtdt.yaml")
        return 1
    space_id = project_id_from_mtdt(mtdt)
    if not space_id:
        log_error(f"{space_dir}: missing project.id")
        return 1

    entry = mounts.get(space_id)
    if not isinstance(entry, dict):
        log_error(
            f"{space_dir}: no space-mounts entry for {space_id} "
            f"(catalog {space_mounts_catalog_path()})"
        )
        return 1

    drift = apply_entry(
        space_dir,
        entry,
        check_only=args.check,
        data_override=args.data,
        root=root,
    )
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
