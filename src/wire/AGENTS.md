# Workspace Instructions

These instructions apply to this projects tree. Personal preferences are maintained separately in the global Codex `AGENTS.md`, maintained in Prompts and deployed through Prompts Space using Dia wiring.

The canonical repository-writing conventions are under `staged/paradigmata/share/conventions/`. Read `README.md`, `plain-text.md`, `path-names.md`, `src-vs-share.md`, and the relevant language-specific convention before creating or editing files.

For every code change, follow `staged/paradigmata/share/conventions/quality-gates.md`. In particular, run the applicable sanitizer and checker on the changed working-tree files before staging, inspect formatter changes, and run the complete pre-commit hook after staging. A formatter-induced hook rejection is not a finished hand-off: review, restage only the task files, and rerun the hook.
