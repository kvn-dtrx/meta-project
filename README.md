# Meta Project

## Synopsis

One project to rule them all: layout of `~/data/projects`, multi-root editor
workspaces, environment plans, space mounts, private mirror remotes, and local Git policy.

Personal catalogues and ops docs live in the private
sibling [meta-project-annex](https://github.com/kvn-dtrx/meta-project-annex).
The separate [mtdt](https://github.com/kvn-dtrx/mtdt) project owns metadata
parsing, discovery, and `.mtdt.local.yaml` deployment.

## Layout

```
src/wire/                   projects tree definition (bin/lns-meta.sh)
src/meta_project/walk.py    mtdt command adapter and private config paths
examples/config/            public env, mount, and remote catalogue examples
Makefile                    make install → every checkout
bin/
  install-checkouts.sh   the projects-tree make install loop
  lns-meta.sh
  setup-state-dirs.sh
  ws.sh
  deploy-env-plans.py
  deploy-git-remotes.py
  deploy-git-info-attributes.py
  mount-space.py         apply private mounts.yaml → <space>/mnt/data
workspaces/                 versioned *.code-workspace files
cache/sessions/             local editor sessions (gitignored)
```

## Roles

| Locus | Owns |
| --- | --- |
| **meta-project** (public) | environment/mount deploy CLIs, layout tooling, checkout `make install` loop |
| **meta-project-annex** (private) | live personal configuration and ops docs |
| **mtdt** | metadata parsing/discovery, schema, overlays, validation, forge checks |
| **krypta** / XDG `envs/*.sh.gpg` | secret material (`retrieve-envvar`) |

## Install checkouts

After macos-habitat bootstrap (`make` exists), this is the loop over the projects tree:

```bash
make -C ~/data/projects/permanent/meta-project install
```

Before installing checkouts, this also merges the private annex catalog at
`src/git/info/attributes` into each checkout's unversioned
`.git/info/attributes`. Existing unrelated local attributes are preserved.

Walks `~/data/projects/permanent` and `staged` (or `META_PROJECTS_ROOT`) for
`.mtdt.yaml`, runs `make install` in each checkout that has that target, and
skips this repo so it cannot recurse. `MTDT_PROJECTS_ROOT` remains a temporary
compatibility alias.

## Install deploy CLIs

```bash
ln -sf ~/data/projects/permanent/meta-project/bin/deploy-env-plans.py \
  ~/.local/bin/deploy-env-plans
ln -sf ~/data/projects/permanent/meta-project/bin/deploy-git-remotes.py \
  ~/.local/bin/deploy-git-remotes
ln -sf ~/data/projects/permanent/meta-project/bin/mount-space.py \
  ~/.local/bin/mount-space
```

Or from this repo (no PATH install required):

```bash
just --list
just deploy-env-plans
just check-env-plans
just deploy-git-remotes
just check-git-remotes
just mount-space-all
just check-space-mounts
just mount-space contacts
```

Environment and mount deployment needs `PyYAML` plus the installed
`mtdt-project-id` / `mtdt-list-projects` commands. Git-policy and checkout
installation remain independently bootstrappable. Catalogues default to
`${XDG_CONFIG_HOME:-~/.config}/meta-project/`. During migration, sources below
`${META_PROJECT_ANNEX}/src/wire/meta-project/config/` and the former Annex
paths remain readable.

```bash
deploy-env-plans ~/data/projects
deploy-env-plans --check ~/data/projects
```

Seed a private annex from `examples/config/*.yaml` if needed. Override the
environment catalogue with `META_PROJECT_ENVS_FILE`; `MTDT_ENV_PLANS_FILE`
remains a compatibility alias.

## Private Git mirror remotes

Operational remotes such as `mirror-glab` and `mirror-nas` are catalogued privately in `~/.config/meta-project/remotes.yaml`, keyed by the stable `project.id`. They are written only to each checkout's local `.git/config`; public `.mtdt.yaml` files remain free of private infrastructure and mirror-role policy.

```bash
just check-git-remotes
just deploy-git-remotes
```

Only explicitly catalogued names beginning with `mirror-` are managed. Unlisted remotes are preserved. Override the catalogue with `META_PROJECT_REMOTES_FILE`.

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
