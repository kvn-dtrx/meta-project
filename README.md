# Meta Project

## Synopsis

One project to rule them all: layout of `~/data/projects`, multi-root editor
workspaces, environment plans, space mounts, derived mirror remotes, and local
Git policy.

Personal catalogues and ops docs live in the private
sibling [meta-project-annex](https://github.com/kvn-dtrx/meta-project-annex).
The separate [mtdt](https://github.com/kvn-dtrx/mtdt) project owns metadata
parsing, discovery, and `.mtdt.local.yaml` deployment.

## Layout

```text
src/wire/                   projects-root files, including AGENTS.md
src/meta_project/walk.py    mtdt command adapter and private config paths
config/forge-rulesets.yaml  shared declarative forge protection profiles
examples/config/            public environment and mount catalogue examples
Makefile                    make install-user/setup-dev → matching checkouts
bin/
  install-checkouts.sh   the projects-tree installation loop
  lns-meta.sh
  setup-state-dirs.sh
  ws.sh
  deploy-env-plans.py
  deploy-git-remotes.py
  deploy-gitlab-avatars.py
  deploy-git-lfs-storage.py
  check-forge-rulesets.py
  repo-recipes.py        list/search Just recipes and Make targets across repos
  deploy-git-info-attributes.py
  mount-space.py         apply private mounts.yaml → <space>/mnt/data
workspaces/                 versioned *.code-workspace files
cache/sessions/             local editor sessions (gitignored)
```

## Roles

| Locus | Owns |
| --- | --- |
| **meta-project** (public) | shared forge policy and deployment tooling |
| **meta-project-annex** (private) | live personal configuration and ops docs |
| **mtdt** | metadata schema, discovery, overlays, validation and forge checks |
| **krypta** / XDG `envs/*.sh.gpg` | secret material (`retrieve-envvar`) |

## Install checkouts

After macos-habitat bootstrap (`make` exists), install user-facing files across
the projects tree:

```bash
make -C ~/data/projects/permanent/meta-project install
```

`install` is an alias for `install-user`. It invokes only checkout
`install-user` targets; system-only installers are excluded.

Walks `~/data/projects/permanent` and `staged` (or `META_PROJECTS_ROOT`) for
`.mtdt.yaml`, runs `make install-user` in each checkout that has that target,
and skips this repo so it cannot recurse. `MTDT_PROJECTS_ROOT` remains a
temporary compatibility alias.

Development setup is explicit:

```bash
make -C ~/data/projects/permanent/meta-project setup-dev
```

This merges the private annex catalogue at `src/git/info/attributes` into each
checkout's unversioned `.git/info/attributes`, then invokes only declared
`setup-dev` targets, such as Krypta's project-local Git-hook installer.
Existing unrelated local attributes are preserved.

User deployment and development setup remain separate; invoke both targets
explicitly when both are wanted. Root installations are never included.

## Install deploy CLIs

```bash
ln -sf ~/data/projects/permanent/meta-project/bin/deploy-env-plans.py \
  ~/.local/bin/deploy-env-plans
ln -sf ~/data/projects/permanent/meta-project/bin/deploy-git-remotes.py \
  ~/.local/bin/deploy-git-remotes
ln -sf ~/data/projects/permanent/meta-project/bin/deploy-gitlab-avatars.py \
  ~/.local/bin/deploy-gitlab-avatars
ln -sf ~/data/projects/permanent/meta-project/bin/deploy-git-lfs-storage.py \
  ~/.local/bin/deploy-git-lfs-storage
ln -sf ~/data/projects/permanent/meta-project/bin/check-forge-rulesets.py \
  ~/.local/bin/check-forge-rulesets
ln -sf ~/data/projects/permanent/meta-project/bin/mount-space.py \
  ~/.local/bin/mount-space
ln -sf ~/data/projects/permanent/meta-project/bin/repo-recipes.py \
  ~/.local/bin/repo-recipes
```

Or from this repo (no PATH install required):

```bash
just --list
just deploy-env-plans
just check-env-plans
just deploy-git-remotes
just check-git-remotes
just deploy-gitlab-avatars
just check-gitlab-avatars
just deploy-git-lfs-storage
just check-git-lfs-storage
just check-github-rulesets
just check-gitlab-rulesets
just repo-recipes notes
just mount-space-all
just check-space-mounts
just mount-space contacts
```

Environment, mount, and remote deployment needs `PyYAML` plus the applicable
installed `mtdt-project-id`, `mtdt-list-projects`, and `resolve-mtdt` commands.
Git-policy and checkout installation remain independently bootstrappable.
Catalogues default to
`${XDG_CONFIG_HOME:-~/.config}/meta-project/`. During migration, sources below
`${META_PROJECT_ANNEX}/src/wire/meta-project/config/` and the former Annex
paths remain readable.

## Repository recipes

`repo-recipes` provides a live catalogue of documented Just recipes and Make targets across the projects tree. It obtains Just signatures and comments from Just's structured dump and reads only statically documented Make targets, so listing Make targets never executes repository code.

```bash
repo-recipes                   # complete catalogue
repo-recipes notes             # search names, commands, and descriptions
repo-recipes --repo git-fleet  # one repository name
repo-recipes --just            # Just recipes only
repo-recipes --make            # Make targets only
repo-recipes --paths           # include checkout paths
```

Only targets carrying a `## description` appear for Make. Private and underscore-prefixed Just recipes, and the conventional `default` recipe, are omitted. The catalogue is evaluated live and therefore requires neither a generated file nor periodic regeneration.

```bash
deploy-env-plans ~/data/projects
deploy-env-plans --check ~/data/projects
```

Seed a private annex from `examples/config/*.yaml` if needed. Override the
environment catalogue with `META_PROJECT_ENVS_FILE`; `MTDT_ENV_PLANS_FILE`
remains a compatibility alias.

## Git remotes

`origin` and `mirror-glab` are derived from each checkout's effective
`forges.github.url` and written as HTTPS URLs only to local `.git/config`.
The local
`.mtdt.local.yaml` forge overlay takes precedence over versioned
`.mtdt.yaml`, so personal forks map to the corresponding personal GitLab
namespace and repository:

```text
https://github.com/OWNER/REPOSITORY
→ origin      https://github.com/OWNER/REPOSITORY.git
→ mirror-glab https://gitlab.com/OWNER/REPOSITORY.git
```

```bash
just check-git-remotes
just deploy-git-remotes
```

Projects without a GitHub forge URL do not receive the managed forge remotes.
Existing additional remotes preserve their forge, owner, and repository;
GitHub/GitLab SSH URLs among them are normalized to HTTPS as well.

Where Git Fleet is installed, the same reconciliation adds a local `nas`
remote. Its URL is derived from the checkout's stable `project.id` and the
host-specific Git Fleet endpoint configuration; neither the NAS host nor its
path is written to project metadata. The required `protocol.ext.allow=always`
setting is likewise confined to local `.git/config`.

## GitLab project avatars

A repository-root `logo.png` is the canonical project logo. The avatar batch
discovers Git checkouts directly and resolves GitLab projects from their
`mirror-glab` remote, falling back to another `gitlab.com` remote. It does not
read `.mtdt.yaml`.

The logo must contain PNG data and be no larger than 200 KiB. Existing GitLab
avatars are preserved unless `--force` is passed:

```bash
just check-gitlab-avatars
just deploy-gitlab-avatars
just deploy-gitlab-avatars --force
```

## Local Git LFS storage

Repositories that declare `filter=lfs` in their root `.gitattributes` receive
a machine-local `lfs.storage` value derived from two versioned facts and one
machine environment root:

```text
${MY_NAS_DATA_DIR}/resources/git-lfs/<GitHub owner>/<repository>
```

The owner and repository come from effective `forges.github.url` metadata,
preserving existing GitHub storage locations. GitHub is optional: when that
URL is absent, null or empty, slugs derived from the first project author and
the project name supply the human-readable identity instead:

```text
${MY_NAS_DATA_DIR}/resources/git-lfs/<author>/<project>
```

This also supports repositories hosted elsewhere. No remote is required or
created. Missing or empty identities are rejected. Renaming an author or
project, or adding a GitHub URL later, changes the derived location; move
existing LFS objects before deploying such a metadata change.
Only the expanded absolute path is written to the checkout's unversioned
`.git/config`; LFS pointers and commits contain no local filesystem path.
`--check` reports missing or divergent configuration without changing it:

```bash
just check-git-lfs-storage
just deploy-git-lfs-storage
```

For a fresh checkout, clone with `GIT_LFS_SKIP_SMUDGE=1`, deploy the local
storage setting, and only then run `git lfs pull`. This avoids first filling
the default `.git/lfs` directory before the NAS policy is installed.

## Forge ruleset policy

[`config/forge-rulesets.yaml`](config/forge-rulesets.yaml) records the shared
desired protection policy once. Every effective mtdt project with a non-null
`forges.github.url` implicitly inherits its `default-profile` on GitHub and on
the derived GitLab mirror; repositories do not repeat the complete policy in
their `.mtdt.yaml`.

Only exceptions need project-local metadata. To opt out deliberately:

```yaml
forges:
  github:
    url: https://github.com/OWNER/REPOSITORY
    ruleset-profile: none
```

To select a future alternative profile, use its catalogue name instead of
`none`. A missing `ruleset-profile` means the central default; an unknown name
is an error. An explicit `forges.gitlab.ruleset-profile` overrides the inherited
selection for GitLab only.

The checks are read-only by default and return a non-zero status for drift:

```bash
just check-github-rulesets
just check-gitlab-rulesets
just check-forge-rulesets
```

`--fix` creates or updates only the managed policy and then checks everything
again. The command re-executes itself through the matching Nitrokey-protected
admin wrapper; checking both forges requests both tokens in sequence:

```bash
just check-github-rulesets --fix
just check-gitlab-rulesets --fix
just check-forge-rulesets --fix
```

GitHub maps the profile to the repository ruleset named
`mtdt/default-branch`. GitLab maps it to default-branch protection with force
push disabled and fast-forward-only merge requests. GitLab has no native rule
for requiring signatures only on the default branch: its Premium/Ultimate
`reject_unsigned_commits` push rule is project-wide and would also reject the
intentionally unsigned `dev/kev` commits. The checker therefore reports this
capability gap as an error and never broadens the policy silently. GitLab branch
protection prevents deletion through Git, but Maintainers can still delete a
protected branch through the GitLab UI or API. No checker deletes rules or
protection automatically.

## Space mounts (`mnt/data`)

Each `*-space` repo keeps `mnt/` (`.gitkeep` force-added). **What** mounts
**where** is catalogued in private meta-project-annex
`~/.config/meta-project/mounts.yaml` (keyed by space `project.id` → data `id` /
`stem`). Public template: `examples/config/mounts.yaml`.

```text
contacts-space/
  mnt/
    .gitkeep          # git add -f
    data → …/contacts # from catalog (single stem)

notes-space/
  mnt/
    .gitkeep
    mint-notes → …
    personal-notes → …
    humanities-notes → …   # catalog `links:` list
```

```bash
ln -sf ~/data/projects/permanent/meta-project/bin/mount-space.py \
  ~/.local/bin/mount-space

mount-space contacts                 # one space (dir, stem, or cwd)
mount-space --all                    # every catalog entry
mount-space --check --all
```

Overrides: `--data DIR`, `META_PROJECT_MOUNTS_FILE`, `META_PROJECTS_ROOT`,
and `META_PROJECT_ANNEX`. The former `MTDT_SPACE_MOUNTS_FILE` and
`MTDT_PROJECTS_ROOT` names remain compatibility aliases.

## Workspaces

```bash
ws              # list
ws notes        # open workspaces/NAME.code-workspace
ws --sessions   # print cache/sessions path
```

```bash
ln -s ~/data/projects/permanent/meta-project/bin/ws.sh ~/.local/bin/ws
```

## Colophon

**Author:** [kvn-dtrx](https://github.com/kvn-dtrx)
