#!/usr/bin/env python3

# ---
# description: >-
#   Reconciles private mirror remotes from the meta-project catalogue
# ---

# ---

# --- Imports ---


import argparse
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from meta_project.walk import (  # noqa: E402
    iter_checkouts,
    load_yaml_mapping,
    log_debug,
    log_error,
    log_info,
    log_warn,
    remotes_catalog_path,
)

# --- Configuration ---


REMOTE_NAME = re.compile(r"^mirror-[A-Za-z0-9._-]+$")

# --- Auxiliary Code ---


def git(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_dir), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def current_urls(project_dir: Path, remote: str) -> list[str]:
    result = git(project_dir, "config", "--get-all", f"remote.{remote}.url")
    if result.returncode not in (0, 1):
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise RuntimeError(detail)
    return result.stdout.splitlines()


def parse_remotes(entry: object) -> dict[str, str]:
    if not isinstance(entry, dict):
        raise ValueError("project entry must be a mapping")
    parsed: dict[str, str] = {}
    for name, spec in entry.items():
        remote = str(name)
        if not REMOTE_NAME.fullmatch(remote):
            raise ValueError(f"remote name must start with mirror-: {remote!r}")
        if not isinstance(spec, dict):
            raise ValueError(f"{remote}: entry must be a mapping")
        raw_url = spec.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ValueError(f"{remote}: non-empty url required")
        parsed[remote] = raw_url.strip()
    return parsed


# --- Main Code ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile private mirror remotes by project.id."
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

    catalog_file = remotes_catalog_path()
    try:
        catalog = load_yaml_mapping(catalog_file)
    except (FileNotFoundError, ValueError) as exc:
        log_error(f"remote catalogue unavailable: {exc}")
        return 1

    plans = catalog.get("remotes")
    if not isinstance(plans, dict):
        log_error(f"{catalog_file}: missing remotes: mapping")
        return 1

    unchanged = added = updated = drift = skipped = errors = 0
    try:
        checkouts = iter_checkouts([Path(root) for root in args.roots])
        for project_dir, project_id in checkouts:
            entry = plans.get(project_id)
            if entry is None:
                skipped += 1
                continue
            try:
                wanted = parse_remotes(entry)
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
            except (RuntimeError, ValueError) as exc:
                log_error(f"{project_dir}: bad remote plan for {project_id}: {exc}")
                errors += 1
    except (FileNotFoundError, RuntimeError) as exc:
        log_error(str(exc))
        return 1

    log_info(
        f"unchanged={unchanged} added={added} updated={updated} "
        f"drift={drift} skipped={skipped} errors={errors} "
        f"catalog={catalog_file}"
    )
    if errors or (args.check and drift):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
