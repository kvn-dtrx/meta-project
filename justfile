# ---
# title: justfile for meta-project
# ---

# ---

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Default tree to scan for .mtdt.yaml / space checkouts
projects := env_var_or_default("META_PROJECTS_ROOT", env_var_or_default("MTDT_PROJECTS_ROOT", home_directory() / "data" / "projects"))

# Shows available recipes
default:
    @just --list --unsorted

# Upserts planned .env keys from the private env catalogue
deploy-env-plans *args:
    @bin/deploy-env-plans.py {{ if args == "" { quote(projects) } else { args } }}

# Reports drift of planned .env keys vs the env catalogue
check-env-plans *args:
    @bin/deploy-env-plans.py --check {{ if args == "" { quote(projects) } else { args } }}

# Reconciles forge remotes and the local NAS depot remote
deploy-git-remotes *args:
    @bin/deploy-git-remotes.py {{ if args == "" { quote(projects) } else { args } }}

# Reports forge and local NAS depot remote drift
check-git-remotes *args:
    @bin/deploy-git-remotes.py --check {{ if args == "" { quote(projects) } else { args } }}

# Uploads missing GitLab avatars from repository-root logo.png files
deploy-gitlab-avatars *args:
    @bin/deploy-gitlab-avatars.py {{ if args == "" { quote(projects) } else { args } }}

# Reports GitLab projects missing an avatar where a root logo.png exists
check-gitlab-avatars *args:
    @bin/deploy-gitlab-avatars.py --check {{ if args == "" { quote(projects) } else { args } }}

# Reconciles repository-local LFS storage below MY_NAS_DATA_DIR
deploy-git-lfs-storage *args:
    @bin/deploy-git-lfs-storage.py {{ if args == "" { quote(projects) } else { args } }}

# Reports local LFS storage drift below MY_NAS_DATA_DIR
check-git-lfs-storage *args:
    @bin/deploy-git-lfs-storage.py --check {{ if args == "" { quote(projects) } else { args } }}

# Checks GitHub default-branch rulesets; pass --fix to reconcile through my-gh admin
check-github-rulesets *args:
    @bin/check-forge-rulesets.py --forge github {{args}} {{quote(projects)}}

# Checks GitLab branch/project/push protections; pass --fix for my-glab admin
check-gitlab-rulesets *args:
    @bin/check-forge-rulesets.py --forge gitlab {{args}} {{quote(projects)}}

# Checks both forge adapters; --fix requests both administrative tokens
check-forge-rulesets *args:
    @bin/check-forge-rulesets.py --forge all {{args}} {{quote(projects)}}

# Links one space mnt/data from the private mount catalogue
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

# Lists and searches documented Just recipes and Make targets across repositories
repo-recipes *args:
    @bin/repo-recipes.py {{args}}
