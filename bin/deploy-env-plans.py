#!/usr/bin/env python3

# ---
# description: >-
#   Upsert planned env keys into checkouts from meta-project env-plans.yaml
#   (by project.id). Values come from XDG env phrase files via retrieve-envvar.
# ---

# ---

# --- Imports ---


import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    sys.stderr.write("deploy-env-plans requires PyYAML\n")
    raise SystemExit(1) from exc

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from mtdt.walk import (  # noqa: E402
    env_plans_catalog_path,
    iter_checkouts,
    load_yaml_mapping,
    log_debug,
    log_error,
    log_info,
    log_warn,
)

# --- Configuration ---

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_./:@%+-]+$")
_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

# --- Auxiliary Code ---


def envs_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local/share"
    return base / "envs"


def phrase_path(stem: str) -> Path:
    name = stem.strip()
    if name.endswith(".gpg"):
        return envs_dir() / name
    if name.endswith(".sh"):
        return envs_dir() / f"{name}.gpg"
    return envs_dir() / f"{name}.sh.gpg"


def retrieve_envvar(var_name: str, phrase: Path) -> str:
    libexec = os.environ.get("XDG_LIBEXEC_HOME", "").strip()
    base = Path(libexec).expanduser() if libexec else Path.home() / ".local/libexec"
    tool = base / "zsh" / "retrieve-envvar"
    if not tool.is_file():
        which = shutil.which("retrieve-envvar")
        if not which:
            raise FileNotFoundError(
                f"retrieve-envvar not found (tried {tool} and PATH)"
            )
        cmd = [which, "-v", var_name, str(phrase)]
    else:
        cmd = [str(tool), "-v", var_name, str(phrase)]

    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"retrieve-envvar -v {var_name} {phrase} failed"
            + (f": {err}" if err else "")
        )
    value = proc.stdout.rstrip("\n")
    if not value:
        raise RuntimeError(f"{var_name} empty after retrieve from {phrase}")
    return value


def format_assignment(key: str, value: str) -> str:
    if _SAFE_VALUE.fullmatch(value):
        return f"{key}={value}"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'{key}="{escaped}"'


def parse_env_lines(text: str) -> tuple[list[str], dict[str, str]]:
    """Keep original lines; map last assignment per key to its value string."""
    lines = text.splitlines()
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _ASSIGN.match(stripped)
        if not m:
            continue
        key, raw = m.group(1), m.group(2)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            values[key] = raw[1:-1]
        else:
            values[key] = raw
    return lines, values


def upsert_env(text: str, updates: dict[str, str]) -> str:
    lines, _ = parse_env_lines(text)
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        m = (
            _ASSIGN.match(stripped)
            if stripped and not stripped.startswith("#")
            else None
        )
        if m and m.group(1) in updates:
            key = m.group(1)
            out.append(format_assignment(key, updates[key]))
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(format_assignment(key, value))
    body = "\n".join(out)
    if body and not body.endswith("\n"):
        body += "\n"
    return body


def plan_vars(entry: dict) -> list[tuple[str, str, str]]:
    """Return list of (env_key, phrase_stem, phrase_var)."""
    raw = entry.get("vars")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("vars must be a list")
    out: list[tuple[str, str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each vars: entry must be a mapping")
        key = item.get("key")
        phrase = item.get("from")
        if not key or not phrase:
            raise ValueError("vars: entries need key: and from:")
        phrase_var = item.get("var") or key
        out.append((str(key), str(phrase), str(phrase_var)))
    return out


# --- Main Code ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Upsert env keys from meta-project env-plans.yaml "
            "(values via retrieve-envvar)."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift only (exit 1 if any); never print secret values",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=["."],
        help="directories to scan (default: .)",
    )
    args = parser.parse_args(argv)

    plans_file = env_plans_catalog_path()
    try:
        catalog = load_yaml_mapping(plans_file)
    except FileNotFoundError:
        log_error(f"env-plans catalog not found: {plans_file}")
        return 1

    plans = catalog.get("plans")
    if not isinstance(plans, dict):
        log_error(f"{plans_file}: missing plans: mapping")
        return 1

    written = unchanged = missing = drift = skipped = errors = 0
    roots = [Path(r) for r in args.roots]

    for project_dir, pid in iter_checkouts(roots):
        entry = plans.get(pid)
        if not isinstance(entry, dict):
            skipped += 1
            continue

        try:
            var_specs = plan_vars(entry)
        except ValueError as exc:
            log_error(f"{project_dir}: bad plan for {pid}: {exc}")
            errors += 1
            continue

        if not var_specs:
            skipped += 1
            continue

        target_name = str(entry.get("target") or ".env")
        target = project_dir / target_name

        updates: dict[str, str] = {}
        retrieve_failed = False
        for env_key, phrase_stem, phrase_var in var_specs:
            phrase = phrase_path(phrase_stem)
            if not phrase.is_file():
                log_error(f"{project_dir}: missing phrase file {phrase}")
                errors += 1
                retrieve_failed = True
                break
            try:
                updates[env_key] = retrieve_envvar(phrase_var, phrase)
            except (FileNotFoundError, RuntimeError) as exc:
                log_error(f"{project_dir}: {exc}")
                errors += 1
                retrieve_failed = True
                break
        if retrieve_failed:
            continue

        if target.is_file():
            text = target.read_text(encoding="utf-8")
            _, have = parse_env_lines(text)
            keys_ok = all(key in have and have[key] == updates[key] for key in updates)
            if keys_ok:
                log_debug(f"ok {target}")
                unchanged += 1
                continue
            if args.check:
                for key in updates:
                    if key not in have:
                        log_warn(f"MISSING_KEY {target} {key}")
                    elif have[key] != updates[key]:
                        log_warn(f"DIVERGE_KEY {target} {key}")
                drift += 1
                continue
            new_text = upsert_env(text, updates)
            target.write_text(new_text, encoding="utf-8")
            os.chmod(target, 0o600)
            log_info(f"updated {target}")
            written += 1
        else:
            if args.check:
                log_warn(f"MISSING {target}")
                for key in updates:
                    log_warn(f"  would set {key}")
                missing += 1
                continue
            new_text = upsert_env("", updates)
            target.write_text(new_text, encoding="utf-8")
            os.chmod(target, 0o600)
            log_info(f"wrote {target}")
            written += 1

    log_info(
        f"unchanged={unchanged} written={written} missing={missing} "
        f"drift={drift} skipped={skipped} errors={errors} catalog={plans_file}"
    )
    if errors:
        return 1
    if args.check and (drift or missing):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
