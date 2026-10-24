#!/usr/bin/env python3

# ---
# description: >-
#   Checks shared mtdt forge protection policy and optionally reconciles it
# ---

# ---

# --- Imports ---


import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self
from urllib.parse import quote, urlsplit

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("forge ruleset checks require PyYAML") from exc

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


DEFAULT_CATALOG = _REPO / "config/forge-rulesets.yaml"
FORGES = ("github", "gitlab")
ADMIN_SENTINELS = {
    "github": ("MY_GH_ADMIN_ACTIVE", "my-gh"),
    "gitlab": ("MY_GLAB_ADMIN_ACTIVE", "my-glab"),
}


# --- Auxiliary Code ---


class ApiError(RuntimeError):
    """A forge CLI API request failed."""


@dataclass
class Counts:
    checked: int = 0
    drift: int = 0
    fixed: int = 0
    skipped: int = 0
    errors: int = 0

    def add(self, other: Self) -> None:
        self.checked += other.checked
        self.drift += other.drift
        self.fixed += other.fixed
        self.skipped += other.skipped
        self.errors += other.errors


class CliApi:
    """Small JSON transport around gh api and glab api."""

    commands = {"github": "gh", "gitlab": "glab"}

    def request(
        self,
        forge: str,
        method: str,
        endpoint: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        executable = self.commands[forge]
        if shutil.which(executable) is None:
            raise ApiError(f"{executable} is not installed")
        command = [executable, "api", endpoint, "--method", method]
        input_text = None
        if body is not None:
            command.extend(["--input", "-"])
            input_text = json.dumps(body, separators=(",", ":"))
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip()
            raise ApiError(f"{forge} {method} {endpoint}: {detail}")
        output = proc.stdout.strip()
        if not output:
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise ApiError(
                f"{forge} {method} {endpoint}: invalid JSON response"
            ) from exc


def load_catalog(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a mapping")
    if data.get("schema-version") != 1:
        raise ValueError(f"{path}: unsupported schema-version")
    default = data.get("default-profile")
    profiles = data.get("profiles")
    if not isinstance(default, str) or not isinstance(profiles, dict):
        raise ValueError(f"{path}: default-profile and profiles are required")
    if default not in profiles:
        raise ValueError(f"{path}: unknown default profile {default!r}")
    for name, profile in profiles.items():
        validate_profile(str(name), profile)
    return data


def validate_profile(name: str, profile: object) -> None:
    if not isinstance(profile, dict):
        raise ValueError(f"profile {name!r} must be a mapping")
    if profile.get("target") != "default-branch":
        raise ValueError(f"profile {name!r}: only default-branch is supported")
    if profile.get("enforcement") != "active":
        raise ValueError(f"profile {name!r}: only active enforcement is supported")
    if profile.get("bypass") != []:
        raise ValueError(f"profile {name!r}: bypass must currently be empty")
    managed_name = profile.get("managed-name")
    if not isinstance(managed_name, str) or not managed_name.startswith("mtdt/"):
        raise ValueError(f"profile {name!r}: managed-name must start with mtdt/")
    require = profile.get("require")
    prohibit = profile.get("prohibit")
    if not isinstance(require, dict) or not isinstance(prohibit, dict):
        raise ValueError(f"profile {name!r}: require and prohibit are required")
    supported_require = {"signed-commits", "linear-history"}
    supported_prohibit = {"deletion", "force-push"}
    if set(require) != supported_require or not all(require.values()):
        raise ValueError(f"profile {name!r}: unsupported require rules")
    if set(prohibit) != supported_prohibit or not all(prohibit.values()):
        raise ValueError(f"profile {name!r}: unsupported prohibit rules")


def forge_path(url: str, host: str) -> str:
    raw = url.strip()
    prefix = f"git@{host}:"
    if raw.startswith(prefix):
        path = raw.removeprefix(prefix)
    else:
        parsed = urlsplit(raw)
        if parsed.scheme not in ("http", "https", "ssh"):
            raise ValueError(f"unsupported {host} URL: {url!r}")
        if parsed.hostname != host or parsed.query or parsed.fragment:
            raise ValueError(f"not a canonical {host} repository URL: {url!r}")
        path = parsed.path.lstrip("/")
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2 or not all(parts) or ".." in parts:
        raise ValueError(f"{host} URL must identify a repository: {url!r}")
    if host == "github.com" and len(parts) != 2:
        raise ValueError(f"GitHub URL must identify owner/repository: {url!r}")
    return "/".join(parts)


def forge_repository(metadata: dict[str, Any], forge: str) -> str | None:
    forges = metadata.get("forges")
    if not isinstance(forges, dict):
        return None
    github = forges.get("github")
    if forge == "github":
        if not isinstance(github, dict):
            return None
        url = github.get("url")
        if url is None or url == "":
            return None
        if not isinstance(url, str):
            raise ValueError("forges.github.url must be a string or null")
        return forge_path(url, "github.com")

    gitlab_present = "gitlab" in forges
    gitlab = forges.get("gitlab")
    if gitlab_present:
        if not isinstance(gitlab, dict):
            return None
        url = gitlab.get("url")
        if url is None or url == "":
            return None
        if not isinstance(url, str):
            raise ValueError("forges.gitlab.url must be a string or null")
        return forge_path(url, "gitlab.com")

    # Current mirror convention: the GitLab project shares the effective
    # GitHub owner and repository path when no explicit GitLab forge exists.
    if not isinstance(github, dict):
        return None
    url = github.get("url")
    if url is None or url == "":
        return None
    if not isinstance(url, str):
        raise ValueError("forges.github.url must be a string or null")
    return forge_path(url, "github.com")


def selected_profile(
    metadata: dict[str, Any], forge: str, catalog: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    forges = metadata.get("forges")
    override: object = None
    if isinstance(forges, dict):
        selected = forges.get(forge)
        if isinstance(selected, dict) and "ruleset-profile" in selected:
            override = selected.get("ruleset-profile")
        elif forge == "gitlab":
            github = forges.get("github")
            if isinstance(github, dict) and "ruleset-profile" in github:
                override = github.get("ruleset-profile")
    name = catalog["default-profile"] if override is None else override
    if name == "none":
        return None
    if not isinstance(name, str):
        raise ValueError(f"forges.{forge}.ruleset-profile must be a string")
    profiles = catalog["profiles"]
    if name not in profiles:
        raise ValueError(f"unknown {forge} ruleset profile {name!r}")
    return name, profiles[name]


def github_payload(profile: dict[str, Any]) -> dict[str, Any]:
    rules: list[dict[str, str]] = []
    if profile["prohibit"]["deletion"]:
        rules.append({"type": "deletion"})
    if profile["prohibit"]["force-push"]:
        rules.append({"type": "non_fast_forward"})
    if profile["require"]["signed-commits"]:
        rules.append({"type": "required_signatures"})
    if profile["require"]["linear-history"]:
        rules.append({"type": "required_linear_history"})
    return {
        "name": profile["managed-name"],
        "target": "branch",
        "enforcement": profile["enforcement"],
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": rules,
    }


def normalized_github_ruleset(data: dict[str, Any]) -> dict[str, Any]:
    conditions = data.get("conditions") or {}
    ref_name = conditions.get("ref_name") or {}
    rules = data.get("rules") or []
    bypass = data.get("bypass_actors") or []
    return {
        "name": data.get("name"),
        "target": data.get("target"),
        "enforcement": data.get("enforcement"),
        "bypass_actors": bypass,
        "conditions": {
            "ref_name": {
                "include": sorted(ref_name.get("include") or []),
                "exclude": sorted(ref_name.get("exclude") or []),
            }
        },
        "rules": sorted(
            ({"type": rule.get("type")} for rule in rules),
            key=lambda rule: str(rule["type"]),
        ),
    }


def reconcile_github(
    api: CliApi,
    repository: str,
    profile: dict[str, Any],
    fix: bool,
) -> Counts:
    counts = Counts(checked=1)
    endpoint = f"repos/{repository}/rulesets"
    listed = api.request("github", "GET", endpoint)
    if not isinstance(listed, list):
        raise ApiError(f"github GET {endpoint}: expected a list")
    matches = [item for item in listed if item.get("name") == profile["managed-name"]]
    expected = github_payload(profile)
    if len(matches) > 1:
        raise ApiError(f"{repository}: duplicate {profile['managed-name']} rulesets")
    if not matches:
        counts.drift += 1
        log_warn(f"DIVERGE github {repository}: managed ruleset missing")
        if fix:
            api.request("github", "POST", endpoint, expected)
            counts.fixed += 1
            log_info(f"fixed github {repository}: created {profile['managed-name']}")
        return counts

    ruleset_id = matches[0].get("id")
    detail = api.request("github", "GET", f"{endpoint}/{ruleset_id}")
    if not isinstance(detail, dict):
        raise ApiError(f"github GET {endpoint}/{ruleset_id}: expected an object")
    if normalized_github_ruleset(detail) != normalized_github_ruleset(expected):
        counts.drift += 1
        log_warn(f"DIVERGE github {repository}: managed ruleset differs")
        if fix:
            api.request("github", "PUT", f"{endpoint}/{ruleset_id}", expected)
            counts.fixed += 1
            log_info(f"fixed github {repository}: updated {profile['managed-name']}")
    else:
        log_debug(f"ok github {repository} {profile['managed-name']}")
    return counts


def reconcile_gitlab(
    api: CliApi,
    repository: str,
    profile: dict[str, Any],
    fix: bool,
) -> Counts:
    counts = Counts(checked=1)
    project_id = quote(repository, safe="")
    project_endpoint = f"projects/{project_id}"
    project = api.request("gitlab", "GET", project_endpoint)
    if not isinstance(project, dict):
        raise ApiError(f"gitlab GET {project_endpoint}: expected an object")
    default_branch = project.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise ApiError(f"gitlab {repository}: project has no default branch")

    protections_endpoint = f"{project_endpoint}/protected_branches?per_page=100"
    protections = api.request("gitlab", "GET", protections_endpoint)
    if not isinstance(protections, list):
        raise ApiError(f"gitlab GET {protections_endpoint}: expected a list")
    matching = [item for item in protections if item.get("name") == default_branch]
    needs_protection = (
        profile["prohibit"]["deletion"] or profile["prohibit"]["force-push"]
    )
    if needs_protection and not matching:
        counts.drift += 1
        log_warn(f"DIVERGE gitlab {repository}: {default_branch} is not protected")
        if fix:
            api.request(
                "gitlab",
                "POST",
                f"{project_endpoint}/protected_branches",
                {
                    "name": default_branch,
                    "push_access_level": 40,
                    "merge_access_level": 40,
                    "allow_force_push": False,
                },
            )
            counts.fixed += 1
            log_info(f"fixed gitlab {repository}: protected {default_branch}")
    elif matching and profile["prohibit"]["force-push"]:
        protection = matching[0]
        if protection.get("allow_force_push") is not False:
            counts.drift += 1
            log_warn(f"DIVERGE gitlab {repository}: force push is allowed")
            if fix:
                branch = quote(default_branch, safe="")
                api.request(
                    "gitlab",
                    "PATCH",
                    f"{project_endpoint}/protected_branches/{branch}",
                    {"allow_force_push": False},
                )
                counts.fixed += 1
                log_info(f"fixed gitlab {repository}: blocked force push")

    if profile["require"]["linear-history"] and project.get("merge_method") != "ff":
        counts.drift += 1
        log_warn(f"DIVERGE gitlab {repository}: merge_method is not ff")
        if fix:
            api.request("gitlab", "PUT", project_endpoint, {"merge_method": "ff"})
            counts.fixed += 1
            log_info(f"fixed gitlab {repository}: merge_method=ff")

    if profile["require"]["signed-commits"]:
        # GitLab's reject_unsigned_commits push rule is project-wide. Enabling
        # it would also reject intentionally unsigned dev/kev commits, so it is
        # not a valid implementation of a default-branch-only policy.
        counts.errors += 1
        log_error(
            f"UNSUPPORTED gitlab {repository}: signed commits cannot be "
            "required only on the default branch"
        )

    if counts.drift == 0:
        log_debug(f"ok gitlab {repository} protected-default")
    return counts


def selected_forges(value: str) -> tuple[str, ...]:
    return FORGES if value == "all" else (value,)


def ensure_admin_execution(forges: tuple[str, ...]) -> None:
    for forge in forges:
        sentinel, wrapper = ADMIN_SENTINELS[forge]
        if os.environ.get(sentinel) == "1":
            continue
        if shutil.which(wrapper) is None:
            raise RuntimeError(f"--fix requires installed {wrapper}")
        command = [
            wrapper,
            "admin-exec",
            sys.executable,
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ]
        os.execvp(wrapper, command)


def run_once(
    api: CliApi,
    roots: list[Path],
    forges: tuple[str, ...],
    catalog: dict[str, Any],
    fix: bool,
) -> Counts:
    total = Counts()
    checkouts = iter_checkouts(roots)
    for project_dir, _project_id in checkouts:
        try:
            metadata = load_effective_metadata(project_dir)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            log_error(f"{project_dir}: cannot load effective mtdt: {exc}")
            total.errors += 1
            continue
        for forge in forges:
            try:
                repository = forge_repository(metadata, forge)
                selection = selected_profile(metadata, forge, catalog)
                if repository is None or selection is None:
                    total.skipped += 1
                    continue
                _name, profile = selection
                if forge == "github":
                    counts = reconcile_github(api, repository, profile, fix)
                else:
                    counts = reconcile_gitlab(api, repository, profile, fix)
                total.add(counts)
            except (ApiError, RuntimeError, ValueError) as exc:
                log_error(f"{project_dir}: {forge} ruleset check failed: {exc}")
                total.errors += 1
    return total


def print_summary(label: str, counts: Counts) -> None:
    log_info(
        f"{label}: checked={counts.checked} drift={counts.drift} "
        f"fixed={counts.fixed} skipped={counts.skipped} errors={counts.errors}"
    )


# --- Main Code ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check GitHub/GitLab default-branch policy from mtdt."
    )
    parser.add_argument(
        "--forge",
        choices=("github", "gitlab", "all"),
        default="all",
        help="forge adapter to check (default: all)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="create or update managed policy, then check again",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help=f"shared profile catalogue (default: {DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[Path.home() / "data/projects"],
        help="project roots to scan",
    )
    args = parser.parse_args(argv)

    try:
        catalog = load_catalog(args.catalog.expanduser())
        forges = selected_forges(args.forge)
        if args.fix:
            ensure_admin_execution(forges)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        log_error(str(exc))
        return 2

    api = CliApi()
    try:
        if args.fix:
            fixed = run_once(api, args.roots, forges, catalog, True)
            print_summary("fix", fixed)
            log_info("rechecking forge rulesets after --fix")
            checked = run_once(api, args.roots, forges, catalog, False)
            print_summary("check", checked)
            if fixed.errors or checked.errors or checked.drift:
                return 1
            return 0

        checked = run_once(api, args.roots, forges, catalog, False)
        print_summary("check", checked)
        return 1 if checked.errors or checked.drift else 0
    except (FileNotFoundError, RuntimeError) as exc:
        log_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
