#!/usr/bin/env python3

# ---
# description: >-
#   Deploy private Repolicy attributes from meta-project-annex into the local
#   Git info directory of every managed checkout
# ---

# ---


import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meta_project.walk import annex_root, iter_git_checkouts, log_error, log_info

BEGIN = "# meta-project:begin repolicy"
END = "# meta-project:end repolicy"


def source_path() -> Path:
    raw = os.environ.get("META_PROJECT_GIT_ATTRIBUTES", "").strip()
    if raw:
        return Path(raw).expanduser()
    return annex_root() / "src/git/info/attributes"


def git_dir(checkout: Path) -> Path | None:
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "--absolute-git-dir"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def rendered(current: str, body: str) -> str:
    lines = current.splitlines()
    try:
        start = lines.index(BEGIN)
    except ValueError:
        start = -1
    try:
        finish = lines.index(END, start + 1) if start >= 0 else -1
    except ValueError as exc:
        raise ValueError(f"found {BEGIN!r} without matching {END!r}") from exc

    block = [BEGIN, *body.rstrip("\n").splitlines(), END]
    if start >= 0:
        lines[start : finish + 1] = block
    else:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(block)
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("roots", nargs="*", type=Path)
    args = parser.parse_args()

    source = source_path()
    if not source.is_file():
        log_error(f"Git attributes source not found: {source}")
        return 1
    body = source.read_text(encoding="utf-8")
    roots = args.roots or [Path.home() / "data/projects"]
    stale = 0

    for checkout in iter_git_checkouts(roots):
        try:
            checkout_git_dir = git_dir(checkout)
            if checkout_git_dir is None:
                continue
            target = checkout_git_dir / "info/attributes"
            current = target.read_text(encoding="utf-8") if target.is_file() else ""
            wanted = rendered(current, body)
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            log_error(f"{checkout}: {exc}")
            return 1
        if current == wanted:
            continue
        stale += 1
        if args.check:
            log_error(f"Git info attributes need deployment: {checkout}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(wanted, encoding="utf-8")
        log_info(f"Deployed Git info attributes: {checkout}")

    return 1 if args.check and stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
