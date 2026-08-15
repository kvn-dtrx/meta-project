# ---
# title: justfile for meta-project
# ---

# ---

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Default tree to scan for .mtdt.yaml / space checkouts
projects := env_var_or_default("MTDT_PROJECTS_ROOT", home_directory() / "data" / "projects")

# Shows available recipes
default:
    @just --list --unsorted

# Writes .mtdt.local.yaml from annex forks catalog
deploy-mtdt-local *args:
    @bin/deploy-mtdt-local.py {{ if args == "" { quote(projects) } else { args } }}

# Reports drift of .mtdt.local.yaml vs forks catalog
check-mtdt-local *args:
    @bin/deploy-mtdt-local.py --check {{ if args == "" { quote(projects) } else { args } }}

# Upserts planned .env keys from annex env-plans (via retrieve-envvar)
deploy-env-plans *args:
    @bin/deploy-env-plans.py {{ if args == "" { quote(projects) } else { args } }}

# Reports drift of planned .env keys vs env-plans catalog
check-env-plans *args:
    @bin/deploy-env-plans.py --check {{ if args == "" { quote(projects) } else { args } }}

# Links one space mnt/data from annex space-mounts (STEM, path, or cwd)
mount-space *args:
    @bin/mount-space.py {{args}}

# Links every catalogued space mnt/data under projects
mount-space-all:
    @bin/mount-space.py --all

# Reports drift of all catalogued space mounts
check-space-mounts:
    @bin/mount-space.py --check --all

# Symlinks src/* entries into ~/data/projects
lns-meta:
    @bin/lns-meta.sh

# Ensures local session/state directories exist
setup-state-dirs:
    @bin/setup-state-dirs.sh

# Opens or lists Cursor/VS Code multi-root workspaces
ws *args:
    @bin/ws.sh {{args}}
