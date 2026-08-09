# Meta Project

## Synopsis

One project to rule them all: layout of `~/data/projects`, multi-root editor
workspaces, and a place for local session state.

## Layout

```
src/                 projects tree definition (symlinked via bin/lns-meta.sh)
bin/
  lns-meta.sh
  setup-state-dirs.sh
  ws.sh              open/list workspaces
workspaces/          versioned *.code-workspace files
cache/sessions/      local editor sessions (gitignored)
```

## Workspaces

```bash
ws              # list
ws notes        # open workspaces/notes.code-workspace
ws --sessions   # print cache/sessions path
```

Override the editor with `WS_OPENER` (default: `cursor`, then `code`).

Install the CLI (once):

```bash
ln -s ~/data/projects/permanent/meta-project/scripts/ws.sh ~/.local/bin/ws
```

## Colophon

**Author:** [kvn-dtrx](https://github.com/kvn-dtrx)
