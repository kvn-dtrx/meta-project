#!/usr/bin/env sh

# ---
# description: Sets up state directories.
# ---

set -e

for dir in "${HOME}/data/projects/"*"/"; do
    touch "${dir}/.gitkeep"
done
