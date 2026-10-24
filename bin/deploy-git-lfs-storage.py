#!/usr/bin/env python3

# ---
# description: >-
#   Reconciles repository-local Git LFS storage below the machine NAS data root
# ---

# ---

# --- Imports ---


import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from meta_project.walk import (  # noqa: E402
    iter_checkouts,
    load_effective_metadata,
    log_debug,
    log_error,
    log_info,
    log_warn,
)

# --- Configuration ---


LFS_ATTRIBUTE = re.compile(r"(?:^|\s)filter=lfs(?:\s|$)")
STORAGE_PREFIX = Path("resources/git-lfs")

# --- Auxiliary Code ---


def git(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_dir), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def declares_lfs(project_dir: Path) -> bool:
    """Recognize the repository-level LFS declaration."""
    attributes = project_dir / ".gitattributes"
    if not attributes.is_file():
        return False
    return any(
        LFS_ATTRIBUTE.search(line) is not None
        for line in attributes.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def github_owner_repo(metadata: dict) -> tuple[str, str]:
    forges = metadata.get("forges")
    github = forges.get("github") if isinstance(forges, dict) else None
    url = github.get("url") if isinstance(github, dict) else None
    if not isinstance(url, str) or not url.strip():
        raise ValueError("LFS repository needs forges.github.url for storage identity")

    raw = url.strip()
    if raw.startswith("git@github.com:"):
        path = raw.removeprefix("git@github.com:")
    else:
        parsed = urlsplit(raw)
        if parsed.scheme not in ("http", "https", "ssh"):
            raise ValueError(f"unsupported GitHub URL: {url!r}")
        if parsed.hostname != "github.com" or parsed.query or parsed.fragment:
            raise ValueError(f"not a canonical github.com repository URL: {url!r}")
        path = parsed.path.lstrip("/")

    parts = path.rstrip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"GitHub URL must identify owner/repository: {url!r}")
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not repository:
        raise ValueError(f"GitHub URL has an empty repository name: {url!r}")
    return owner, repository


def storage_slug(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"LFS storage requires a non-empty {label}")
    slug = value.strip().replace(": ", "_")
    slug = re.sub(r"(?<=[a-z])\.(?=[a-z])", "-", slug)
    slug = slug.replace(".", "")
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "", slug)
    slug = re.sub(r"-{2,}", "-", slug.lower())
    slug = re.sub(r"^[-_]+|[-_]+$", "", slug)
    if not slug:
        raise ValueError(f"{label} produces an empty LFS storage slug")
    return slug


def local_owner_repo(metadata: dict) -> tuple[str, str]:
    project = metadata.get("project")
    if not isinstance(project, dict):
        raise ValueError("Local LFS storage requires project metadata")

    author = project.get("author")
    if not isinstance(author, str) or not author.strip():
        authors = project.get("authors")
        first = authors[0] if isinstance(authors, list) and authors else None
        author = first.get("name") if isinstance(first, dict) else None

    return (
        storage_slug(author, "project author"),
        storage_slug(project.get("name"), "project name"),
    )


def desired_storage(data_root: Path, metadata: dict) -> Path:
    forges = metadata.get("forges")
    github = forges.get("github") if isinstance(forges, dict) else None
    url = github.get("url") if isinstance(github, dict) else None
    if url is not None and url != "":
        owner, repository = github_owner_repo(metadata)
        return data_root / STORAGE_PREFIX / owner / repository

    owner, repository = local_owner_repo(metadata)
    return data_root / STORAGE_PREFIX / owner / repository


def current_storage(project_dir: Path) -> str | None:
    result = git(project_dir, "config", "--local", "--get", "lfs.storage")
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise RuntimeError(detail)
    return result.stdout.rstrip("\n")


def set_storage(project_dir: Path, storage: Path) -> None:
    result = git(
        project_dir,
        "config",
        "--local",
        "lfs.storage",
        str(storage),
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise RuntimeError(detail)


def data_root_from_args(value: str | None) -> Path:
    raw = (value or os.environ.get("MY_NAS_DATA_DIR", "")).strip()
    if not raw:
        raise ValueError("MY_NAS_DATA_DIR is unset; mount and declare the NAS first")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ValueError("MY_NAS_DATA_DIR must be an absolute path")
    if not root.is_dir():
        raise ValueError(f"NAS data root is unavailable: {root}")
    return root


# --- Main Code ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile local LFS storage below MY_NAS_DATA_DIR."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift without changing local Git configuration",
    )
    parser.add_argument(
        "--data-root",
        help="override MY_NAS_DATA_DIR for this invocation",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=["."],
        help="directories to scan (default: .)",
    )
    args = parser.parse_args(argv)

    try:
        data_root = data_root_from_args(args.data_root)
    except ValueError as exc:
        log_error(str(exc))
        return 1

    unchanged = updated = drift = skipped = errors = 0
    try:
        checkouts = iter_checkouts([Path(root) for root in args.roots])
        for project_dir, _project_id in checkouts:
            if not declares_lfs(project_dir):
                skipped += 1
                continue
            try:
                wanted = desired_storage(
                    data_root,
                    load_effective_metadata(project_dir),
                )
                current = current_storage(project_dir)
                if current == str(wanted):
                    log_debug(f"ok {project_dir} lfs.storage")
                    unchanged += 1
                    continue
                if args.check:
                    log_warn(
                        f"DIVERGE {project_dir} lfs.storage: "
                        f"{current or 'missing'} -> {wanted}"
                    )
                    drift += 1
                    continue
                wanted.mkdir(parents=True, exist_ok=True)
                set_storage(project_dir, wanted)
                log_info(f"updated {project_dir} lfs.storage -> {wanted}")
                updated += 1
            except (OSError, RuntimeError, ValueError) as exc:
                log_error(f"{project_dir}: cannot reconcile LFS storage: {exc}")
                errors += 1
    except (FileNotFoundError, RuntimeError) as exc:
        log_error(str(exc))
        return 1

    log_info(
        f"unchanged={unchanged} updated={updated} drift={drift} "
        f"skipped={skipped} errors={errors}"
    )
    if errors or (args.check and drift):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
