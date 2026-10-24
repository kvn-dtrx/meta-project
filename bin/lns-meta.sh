#!/usr/bin/env sh

# ---
# description: >-
#   Creates symbolic links in a designated projects directory for each
#   item found in the repository's source folder
# ---

# ---

set -o errexit
set -o nounset

find_mtdt_root() (
    start="${1:-${PWD}}"
    root="$(CDPATH='' cd -- "${start}" 2> /dev/null && pwd -P)" || return 1
    while [ ! -f "${root}/.mtdt.yaml" ]; do
        parent="$(dirname "${root}")"
        if [ "${parent}" = "${root}" ]; then
            printf 'No .mtdt.yaml found above %s\n' "${start}" >&2
            return 1
        fi
        root="${parent}"
    done
    printf '%s\n' "${root}"
)

DST_DIR="${HOME}/data/projects"

script_path="$(realpath "${0}")"
script_dir="$(dirname "${script_path}")"
repo_dir="$(find_mtdt_root "${script_dir}")"

find -L "${repo_dir}"/src/wire -mindepth 1 -maxdepth 1 |
    while IFS="" read -r source; do
        dst_name="$(basename "${source}")"
        target="${DST_DIR}/${dst_name}"
        ln -s -f "${source}" "${target}"
    done
