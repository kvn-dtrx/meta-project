#!/usr/bin/env sh

# ---
# description: >-
#   Sets up state directories
# ---

# ---

set -o errexit
set -o nounset

for dir in "${HOME}/data/projects/"*"/"; do
    touch "${dir}/.gitkeep"
done
