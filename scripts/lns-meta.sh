#!/usr/bin/env sh

# ---
# description:
# ---

set -e

TARGET_DIR="${HOME}/data/projects"

script_path="$(realpath "${0}")"
script_dir="$(dirname "${script_path}")"
repo_dir="$(git -C "${script_dir}" rev-parse --show-toplevel)"

for source in "${repo_dir}/meta"/*; do
    target_name="$(basename "${source}")"
    target="${TARGET_DIR}/${target_name}"
    ln -s "${source}" "${target}"
done
