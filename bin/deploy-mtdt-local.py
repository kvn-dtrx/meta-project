#!/usr/bin/env python3

# ---
# description: >-
#   Deploy .mtdt.local.yaml into checkouts from meta-project forks.yaml
#   (matched by project.id). Default writes; --check reports drift only.
# ---

# ---

# --- Imports ---


import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    sys.stderr.write("deploy-mtdt-local requires PyYAML\n")
    raise SystemExit(1) from exc

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from mtdt.walk import (  # noqa: E402
    forks_catalog_path,
    iter_checkouts,
    load_yaml_mapping,
    log_debug,
    log_error,
    log_info,
    log_warn,
)

# --- Auxiliary Code ---


def expected_local(entry: dict) -> dict | None:
    github = entry.get("github")
    if not isinstance(github, dict):
        return None
    url = github.get("url")
    if not url or url == "null":
        return None
    vis = github.get("visibility", None)
    out_github: dict = {"url": str(url)}
    if vis is None or vis == "null":
        out_github["visibility"] = None
    else:
        out_github["visibility"] = vis
    return {"forges": {"github": out_github}}


def dump_local(data: dict) -> str:
    return yaml.safe_dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def canonical(data: dict) -> str:
    return yaml.safe_dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )


# --- Main Code ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Write .mtdt.local.yaml from meta-project forks.yaml (by project.id)."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift only (exit 1 if any)",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=["."],
        help="directories to scan (default: .)",
    )
    args = parser.parse_args(argv)

    forks_file = forks_catalog_path()
    try:
        catalog = load_yaml_mapping(forks_file)
    except FileNotFoundError:
        log_error(f"forks catalog not found: {forks_file}")
        return 1

    forks = catalog.get("forks")
    if not isinstance(forks, dict):
        log_error(f"{forks_file}: missing forks: mapping")
        return 1

    written = unchanged = missing = drift = skipped = 0
    roots = [Path(r) for r in args.roots]

    for project_dir, pid in iter_checkouts(roots):
        entry = forks.get(pid)
        if not isinstance(entry, dict):
            skipped += 1
            continue

        want = expected_local(entry)
        if want is None:
            log_error(f"{project_dir}: catalog entry {pid} missing github.url")
            drift += 1
            continue

        local_file = project_dir / ".mtdt.local.yaml"
        want_text = dump_local(want)

        if local_file.is_file():
            have = yaml.safe_load(local_file.read_text(encoding="utf-8"))
            if isinstance(have, dict) and canonical(have) == canonical(want):
                log_debug(f"ok {project_dir}")
                unchanged += 1
                continue
            if args.check:
                log_warn(f"DIVERGE {project_dir}")
                log_warn(f"  catalog id {pid} ≠ {local_file}")
                drift += 1
                continue
            local_file.write_text(want_text, encoding="utf-8")
            log_info(f"updated {local_file}")
            written += 1
        else:
            if args.check:
                log_warn(f"MISSING {project_dir}")
                log_warn(f"  would write .mtdt.local.yaml for {pid}")
                missing += 1
                continue
            local_file.write_text(want_text, encoding="utf-8")
            log_info(f"wrote {local_file}")
            written += 1

    log_info(
        f"unchanged={unchanged} written={written} missing={missing} "
        f"drift={drift} skipped={skipped} catalog={forks_file}"
    )
    if args.check and (drift or missing):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
