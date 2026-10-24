#!/usr/bin/env python3

# ---
# description: >-
#   Reconciles HTTPS forge remotes from effective mtdt metadata
# ---

# ---

# --- Imports ---


import argparse
import os
import shutil
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


ORIGIN_NAME = "origin"
MIRROR_NAME = "mirror-glab"
FLEET_REMOTE_NAME = "nas"

# --- Auxiliary Code ---


def git(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_dir), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def is_git_checkout(project_dir: Path) -> bool:
    result = git(project_dir, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def current_values(project_dir: Path, key: str) -> list[str]:
    result = git(project_dir, "config", "--get-all", key)
    if result.returncode not in (0, 1):
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise RuntimeError(detail)
    return result.stdout.splitlines()


def current_urls(project_dir: Path, remote: str) -> list[str]:
    return current_values(project_dir, f"remote.{remote}.url")


def remote_names(project_dir: Path) -> list[str]:
    result = git(project_dir, "remote")
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise RuntimeError(detail)
    return result.stdout.splitlines()


def github_owner_repo(url: str) -> tuple[str, str]:
    """Return owner/repository from common github.com URL forms."""
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


def ssh_forge_to_https(url: str) -> str | None:
    """Convert a GitHub/GitLab SSH URL to HTTPS without changing its path."""
    raw = url.strip()
    host = ""
    path = ""
    for candidate in ("github.com", "gitlab.com"):
        prefix = f"git@{candidate}:"
        if raw.startswith(prefix):
            host = candidate
            path = raw.removeprefix(prefix)
            break
    if not host:
        parsed = urlsplit(raw)
        if parsed.scheme != "ssh" or parsed.hostname not in (
            "github.com",
            "gitlab.com",
        ):
            return None
        host = parsed.hostname
        path = parsed.path.lstrip("/")
    if not path or path.startswith("/") or ".." in path.split("/"):
        raise ValueError(f"invalid SSH forge URL path: {url!r}")
    return f"https://{host}/{path}"


def github_url(metadata: dict) -> str | None:
    forges = metadata.get("forges")
    if not isinstance(forges, dict):
        return None
    github = forges.get("github")
    if not isinstance(github, dict):
        return None
    github_url = github.get("url")
    if github_url is None or github_url == "":
        return None
    if not isinstance(github_url, str):
        raise ValueError("forges.github.url must be a string or null")
    owner, repository = github_owner_repo(github_url)
    return f"https://github.com/{owner}/{repository}.git"


def git_fleet_remote_url(project_dir: Path) -> str:
    command = os.environ.get("GIT_FLEET_COMMAND", "").strip()
    if not command:
        command = shutil.which("git-fleet") or ""
    if not command:
        raise FileNotFoundError("git-fleet not found; install the git-fleet repository")
    result = subprocess.run(
        [command, "remote-url", FLEET_REMOTE_NAME, str(project_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise RuntimeError(f"git-fleet remote-url failed: {detail}")
    url = result.stdout.strip()
    if not url:
        raise RuntimeError("git-fleet remote-url returned an empty URL")
    return url


def desired_remotes(metadata: dict, *, fleet_url: str | None = None) -> dict[str, str]:
    origin = github_url(metadata)
    remotes: dict[str, str] = {}
    if origin is not None:
        owner, repository = github_owner_repo(origin)
        remotes.update(
            {
                ORIGIN_NAME: origin,
                MIRROR_NAME: f"https://gitlab.com/{owner}/{repository}.git",
            }
        )
    if fleet_url is not None:
        remotes[FLEET_REMOTE_NAME] = fleet_url
    return remotes


# --- Main Code ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile HTTPS origin and mirror-glab forge remotes."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift without changing Git configuration",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=["."],
        help="directories to scan (default: .)",
    )
    args = parser.parse_args(argv)

    unchanged = added = updated = drift = skipped = errors = 0
    try:
        checkouts = iter_checkouts([Path(root) for root in args.roots])
        for project_dir, _project_id in checkouts:
            try:
                if not is_git_checkout(project_dir):
                    skipped += 1
                    continue
                wanted = desired_remotes(
                    load_effective_metadata(project_dir),
                    fleet_url=git_fleet_remote_url(project_dir),
                )
                for remote in remote_names(project_dir):
                    if remote in wanted:
                        continue
                    urls = current_urls(project_dir, remote)
                    converted = [ssh_forge_to_https(url) for url in urls]
                    converted = [url for url in converted if url is not None]
                    if not converted:
                        continue
                    if len(urls) != 1:
                        raise ValueError(
                            f"{remote}: multiple URLs are not managed safely"
                        )
                    wanted[remote] = converted[0]
                if not wanted:
                    skipped += 1
                    continue
                for remote, url in wanted.items():
                    urls = current_urls(project_dir, remote)
                    if urls == [url]:
                        log_debug(f"ok {project_dir} {remote}")
                        unchanged += 1
                        continue
                    if len(urls) > 1:
                        raise ValueError(
                            f"{remote}: multiple URLs are not managed safely"
                        )
                    if args.check:
                        current = urls[0] if urls else "missing"
                        log_warn(f"DIVERGE {project_dir} {remote}: {current} -> {url}")
                        drift += 1
                    elif urls:
                        result = git(project_dir, "remote", "set-url", remote, url)
                        if result.returncode != 0:
                            raise RuntimeError(result.stderr.strip())
                        log_info(f"updated {project_dir} {remote} -> {url}")
                        updated += 1
                    else:
                        result = git(project_dir, "remote", "add", remote, url)
                        if result.returncode != 0:
                            raise RuntimeError(result.stderr.strip())
                        log_info(f"added {project_dir} {remote} -> {url}")
                        added += 1
                protocol = current_values(project_dir, "protocol.ext.allow")
                if protocol != ["always"]:
                    if args.check:
                        current = protocol[0] if protocol else "missing"
                        log_warn(
                            f"DIVERGE {project_dir} protocol.ext.allow: "
                            f"{current} -> always"
                        )
                        drift += 1
                    else:
                        result = git(
                            project_dir, "config", "protocol.ext.allow", "always"
                        )
                        if result.returncode != 0:
                            raise RuntimeError(result.stderr.strip())
                        log_info(f"updated {project_dir} protocol.ext.allow -> always")
                        updated += 1
            except (RuntimeError, ValueError) as exc:
                log_error(f"{project_dir}: cannot reconcile forge remotes: {exc}")
                errors += 1
    except (FileNotFoundError, RuntimeError) as exc:
        log_error(str(exc))
        return 1

    log_info(
        f"unchanged={unchanged} added={added} updated={updated} "
        f"drift={drift} skipped={skipped} errors={errors}"
    )
    if errors or (args.check and drift):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
