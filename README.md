# Meta Project

## Synopsis

One project to rule them all: layout of `~/data/projects`, multi-root editor
workspaces, and deploy CLIs for clone-local catalogs.

Personal catalogs (fork overlays, env plans) and ops docs live in the private
sibling [meta-project-annex](https://github.com/kvn-dtrx/meta-project-annex).

## Layout

```
src/                        projects tree definition (bin/lns-meta.sh)
src/mtdt/walk.py            shared checkout walk for deploy CLIs
share/templates/mtdt/       example catalog templates (not live data)
Makefile                    make install → every checkout
bin/
  install-checkouts.sh   the projects-tree make install loop
  lns-meta.sh
  setup-state-dirs.sh
  ws.sh
  deploy-mtdt-local.py
  deploy-env-plans.py
  deploy-git-info-attributes.py
  mount-space.py         apply annex space-mounts.yaml → <space>/mnt/data
workspaces/                 versioned *.code-workspace files
cache/sessions/             local editor sessions (gitignored)
```

## Roles

| Locus | Owns |
| --- | --- |
| **meta-project** (public) | deploy CLIs, templates, layout tooling, checkout `make install` loop |
| **meta-project-annex** (private) | live `forks.yaml` / `env-plans.yaml`, personal docs |
| **mtdt** | `.mtdt.yaml` schema, resolve, validate, forge checks |
| **krypta** / XDG `envs/*.sh.gpg` | secret material (`retrieve-envvar`) |

## Install checkouts

After macos-habitat bootstrap (`make` exists), this is the loop over the projects tree:

```bash
make -C ~/data/projects/permanent/meta-project install
```

Before installing checkouts, this also merges the private annex catalog at
`src/git/info/attributes` into each checkout's unversioned
`.git/info/attributes`. Existing unrelated local attributes are preserved.

Walks `~/data/projects/permanent` and `staged` (or `MTDT_PROJECTS_ROOT`) for `.mtdt.yaml`, runs `make install` in each checkout that has that target, and skips this repo so it cannot recurse.

## Install deploy CLIs

```bash
ln -sf ~/data/projects/permanent/meta-project/bin/deploy-mtdt-local.py \
  ~/.local/bin/deploy-mtdt-local
ln -sf ~/data/projects/permanent/meta-project/bin/deploy-env-plans.py \
  ~/.local/bin/deploy-env-plans
ln -sf ~/data/projects/permanent/meta-project/bin/mount-space.py \
  ~/.local/bin/mount-space
```

Or from this repo (no PATH install required):

```bash
just --list
just deploy-mtdt-local          # default: ~/data/projects
just check-mtdt-local
just deploy-env-plans
just check-env-plans
just mount-space-all
just check-space-mounts
just mount-space contacts
```

Needs `PyYAML`. Catalogs default to
`${META_PROJECT_ANNEX:-~/data/projects/permanent/meta-project-annex}/src/mtdt/`.
Override with `META_PROJECT_ANNEX`, `MTDT_FORKS_FILE`, or `MTDT_ENV_PLANS_FILE`.

```bash
deploy-mtdt-local ~/data/projects
deploy-mtdt-local --check ~/data/projects
deploy-env-plans ~/data/projects
deploy-env-plans --check ~/data/projects
```

Seed a private annex from `share/templates/mtdt/*.example.yaml` if needed.

## Space mounts (`mnt/data`)

Each `*-space` repo keeps `mnt/` (`.gitkeep` force-added). **What** mounts
**where** is catalogued in private meta-project-annex
`src/mtdt/space-mounts.yaml` (keyed by space `project.id` → data `id` /
`stem`). Public template: `share/templates/mtdt/space-mounts.example.yaml`.

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

Overrides: `--data DIR`, `MTDT_SPACE_MOUNTS_FILE`, `MTDT_PROJECTS_ROOT`,
`META_PROJECT_ANNEX`.

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
