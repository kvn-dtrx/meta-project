#!/usr/bin/env python3

# ---
# description: >-
#   Reconciles GitLab project avatars from repository-root logo.png files
# ---


import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, urlsplit

LOGO_BASENAME = "logo.png"
MAX_AVATAR_BYTES = 200 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "venv"}
PREFERRED_REMOTES = ("mirror-glab", "gitlab")
_SCP_URL = re.compile(r"^(?:[^@]+@)?(?P<host>[^:]+):(?P<path>.+)$")


class GlabError(RuntimeError):
    """A GitLab CLI operation failed."""


def log_info(message: str) -> None:
    print(f"[INFO]:  {message}")


def log_debug(message: str) -> None:
    print(f"[DEBUG]: {message}")


def log_warn(message: str) -> None:
    print(f"[WARN]:  {message}", file=sys.stderr)


def log_error(message: str) -> None:
    print(f"[ERROR]: {message}", file=sys.stderr)


def iter_repositories(roots: list[Path]) -> Iterator[Path]:
    """Yield outer Git checkouts, stopping before nested repositories."""
    seen: set[Path] = set()
    for supplied in roots:
        root = supplied.expanduser()
        if not root.exists():
            continue
        if root.is_file():
            root = root.parent
        for dirpath, dirnames, filenames in os.walk(root):
            directory = Path(dirpath)
            if ".git" in dirnames or ".git" in filenames:
                resolved = directory.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield resolved
                dirnames.clear()
                continue
            dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)


def git(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_dir), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def remote_names(project_dir: Path) -> list[str]:
    result = git(project_dir, "remote")
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise RuntimeError(f"cannot list Git remotes: {detail}")
    return sorted(line for line in result.stdout.splitlines() if line)


def remote_urls(project_dir: Path, remote: str) -> list[str]:
    result = git(project_dir, "remote", "get-url", "--all", remote)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise RuntimeError(f"cannot read Git remote {remote!r}: {detail}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def forge_target(url: str) -> tuple[str, str]:
    raw = url.strip()
    scp_match = _SCP_URL.fullmatch(raw) if "://" not in raw else None
    if scp_match is not None:
        hostname = scp_match.group("host")
        path = scp_match.group("path")
    else:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https", "ssh"} or not parsed.hostname:
            raise ValueError(f"unsupported forge URL: {url!r}")
        if parsed.query or parsed.fragment:
            raise ValueError(f"forge URL must not contain query or fragment: {url!r}")
        hostname = parsed.hostname
        path = parsed.path.lstrip("/")
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if len(path.split("/")) < 2 or any(not part for part in path.split("/")):
        raise ValueError(f"forge URL must identify namespace/project: {url!r}")
    return hostname.lower(), path


def gitlab_target(project_dir: Path) -> tuple[str, str] | None:
    names = remote_names(project_dir)
    for preferred in PREFERRED_REMOTES:
        if preferred not in names:
            continue
        urls = remote_urls(project_dir, preferred)
        if len(urls) != 1:
            raise ValueError(f"remote {preferred!r} must have exactly one URL")
        target = forge_target(urls[0])
        if target[0] != "gitlab.com":
            raise ValueError(f"remote {preferred!r} does not target gitlab.com")
        return target

    candidates: set[tuple[str, str]] = set()
    for remote in names:
        for url in remote_urls(project_dir, remote):
            try:
                target = forge_target(url)
            except ValueError:
                continue
            if target[0] == "gitlab.com":
                candidates.add(target)
    if len(candidates) > 1:
        rendered = ", ".join(f"{host}/{path}" for host, path in sorted(candidates))
        raise ValueError(f"multiple GitLab projects found: {rendered}")
    return next(iter(candidates), None)


def project_logo(project_dir: Path) -> Path | None:
    path = project_dir / LOGO_BASENAME
    if not path.is_file():
        return None
    size = path.stat().st_size
    if size > MAX_AVATAR_BYTES:
        raise ValueError(
            f"{path}: GitLab project avatars must be at most 200 KiB "
            f"(found {size} bytes)"
        )
    with path.open("rb") as stream:
        signature = stream.read(len(PNG_SIGNATURE))
    if signature != PNG_SIGNATURE:
        raise ValueError(f"{path}: expected PNG data")
    return path


def run_glab(
    project_dir: Path, hostname: str, endpoint: str, *args: str
) -> subprocess.CompletedProcess[str]:
    if shutil.which("glab") is None:
        raise GlabError("glab is not installed")
    return subprocess.run(
        ["glab", "api", endpoint, "--hostname", hostname, *args],
        cwd=project_dir,
        check=False,
        capture_output=True,
        text=True,
    )


def live_project(project_dir: Path, hostname: str, path: str) -> tuple[dict, str]:
    endpoint = f"projects/{quote(path, safe='')}"
    result = run_glab(project_dir, hostname, endpoint, "--output", "json")
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise GlabError(f"cannot read {hostname}/{path}: {detail}")
    try:
        project = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GlabError(f"invalid JSON while reading {hostname}/{path}") from exc
    if not isinstance(project, dict):
        raise GlabError(f"GitLab returned no project object for {hostname}/{path}")
    return project, endpoint


def upload_avatar(
    project_dir: Path,
    hostname: str,
    endpoint: str,
    logo: Path,
) -> str:
    boundary = f"----meta-project-{secrets.token_hex(16)}"
    marker = boundary.encode("ascii")
    payload = (
        b"--"
        + marker
        + b'\r\nContent-Disposition: form-data; name="avatar"; filename="logo.png"'
        + b"\r\nContent-Type: image/png\r\n\r\n"
        + logo.read_bytes()
        + b"\r\n--"
        + marker
        + b"--\r\n"
    )
    with tempfile.NamedTemporaryFile(
        prefix="meta-project-avatar-", suffix=".multipart"
    ) as body:
        body.write(payload)
        body.flush()
        result = run_glab(
            project_dir,
            hostname,
            endpoint,
            "--method",
            "PUT",
            "--header",
            f"Content-Type: multipart/form-data; boundary={boundary}",
            "--input",
            body.name,
            "--output",
            "json",
        )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise GlabError(f"avatar upload failed for {hostname}/{endpoint}: {detail}")
    try:
        project = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GlabError("invalid JSON after avatar upload") from exc
    avatar_url = project.get("avatar_url") if isinstance(project, dict) else None
    if not isinstance(avatar_url, str) or not avatar_url:
        raise GlabError("GitLab did not report an avatar after upload")
    return avatar_url


def sync_avatar(project_dir: Path, *, check: bool, force: bool) -> str:
    logo = project_logo(project_dir)
    if logo is None:
        return "skipped"
    target = gitlab_target(project_dir)
    if target is None:
        log_debug(f"skip {project_dir}: no GitLab remote")
        return "skipped"
    hostname, path = target
    live, endpoint = live_project(project_dir, hostname, path)
    current = live.get("avatar_url")
    if isinstance(current, str) and current and not force:
        return "unchanged"
    action = "replace" if current else "upload"
    if check:
        log_warn(f"DIVERGE {hostname}/{path}: avatar {action} <- {logo}")
        return "drift"
    upload_avatar(project_dir, hostname, endpoint, logo)
    completed = "replaced" if current else "uploaded"
    log_info(f"{hostname}/{path}: avatar {completed} <- {logo.name}")
    return "updated"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile GitLab avatars from repository-root logo.png files."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report missing avatars without changing GitLab",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace avatars already set on GitLab",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[Path.cwd()],
        help="directories containing Git repositories (default: .)",
    )
    args = parser.parse_args(argv)

    counts = {"unchanged": 0, "updated": 0, "drift": 0, "skipped": 0, "errors": 0}
    for project_dir in iter_repositories(args.roots):
        try:
            outcome = sync_avatar(project_dir, check=args.check, force=args.force)
            counts[outcome] += 1
        except (GlabError, OSError, RuntimeError, ValueError) as exc:
            log_error(f"{project_dir}: {exc}")
            counts["errors"] += 1

    log_info(" ".join(f"{key}={value}" for key, value in counts.items()))
    return 1 if counts["errors"] or (args.check and counts["drift"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
