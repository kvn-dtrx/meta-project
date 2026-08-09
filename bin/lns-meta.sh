#!/usr/bin/env sh

# ---
# description: >-
#   Creates symbolic links in a designated projects directory for each
#   item found in the repository's source folder
# ---

# ---

set -o errexit
set -o nounset

DST_DIR="${HOME}/data/projects"

script_path="$(realpath "${0}")"
script_dir="$(dirname "${script_path}")"
repo_dir="$(git -C "${script_dir}" rev-parse --show-toplevel)"

find -L "${repo_dir}"/src -mindepth 1 |
    while IFS="" read -r source; do
        dst_name="$(basename "${source}")"
        target="${DST_DIR}/${dst_name}"
        ln -s -f "${source}" "${target}"
    done
