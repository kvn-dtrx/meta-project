#!/usr/bin/env sh

# ---
# description: >-
#   Opens a Cursor/VS Code multi-root workspace from workspaces/, or lists
#   available workspaces. Session files live under cache/sessions/.
# ---

# ---

set -o errexit
set -o nounset

script_path="$(realpath "${0}")"
script_dir="$(dirname "${script_path}")"
repo_dir="$(git -C "${script_dir}" rev-parse --show-toplevel)"
workspaces_dir="${repo_dir}/workspaces"
sessions_dir="${repo_dir}/cache/sessions"

usage() {
    printf 'usage: %s [NAME | --list | --sessions]\n' "$(basename "${0}")" >&2
    printf '  NAME         open workspaces/NAME.code-workspace\n' >&2
    printf '  --list, -l   list available workspaces (default)\n' >&2
    printf '  --sessions   print cache/sessions path\n' >&2
}

list_workspaces() {
    if ! ls "${workspaces_dir}"/*.code-workspace >/dev/null 2>&1; then
        printf 'no workspaces in %s\n' "${workspaces_dir}" >&2
        return 1
    fi
    for f in "${workspaces_dir}"/*.code-workspace; do
        basename "${f}" .code-workspace
    done
}

ensure_sessions() {
    mkdir -p \
        "${sessions_dir}/cursor" \
        "${sessions_dir}/nvim" \
        "${sessions_dir}/emacs"
}

resolve_opener() {
    if [ -n "${WS_OPENER:-}" ]; then
        printf '%s' "${WS_OPENER}"
        return
    fi
    if command -v cursor >/dev/null 2>&1; then
        printf 'cursor'
        return
    fi
    if command -v code >/dev/null 2>&1; then
        printf 'code'
        return
    fi
    printf 'no opener found (set WS_OPENER, or install cursor/code)\n' >&2
    return 1
}

open_workspace() {
    name="${1%.code-workspace}"
    file="${workspaces_dir}/${name}.code-workspace"
    if [ ! -f "${file}" ]; then
        printf 'workspace not found: %s\n' "${name}" >&2
        printf 'available:\n' >&2
        list_workspaces >&2 || true
        return 1
    fi
    ensure_sessions
    opener="$(resolve_opener)"
    exec "${opener}" "${file}"
}

case "${1:-}" in
    '' | -l | --list)
        list_workspaces
        ;;
    -h | --help)
        usage
        ;;
    --sessions)
        ensure_sessions
        printf '%s\n' "${sessions_dir}"
        ;;
    -*)
        usage
        exit 2
        ;;
    *)
        open_workspace "${1}"
        ;;
esac
