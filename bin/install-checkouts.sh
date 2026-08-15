#!/bin/sh

# ---
# description: >-
#   Runs make install in each permanent/staged checkout that has that
#   target. Skips this repo so make install here cannot recurse.
# ---

# ---

set -o nounset

self="$(CDPATH='' cd -- "$(dirname "${0}")/.." && pwd)"

if [ -n "${MTDT_PROJECTS_ROOT:-}" ]; then
    set -- "${MTDT_PROJECTS_ROOT}"
else
    set -- \
        "${HOME}/data/projects/permanent" \
        "${HOME}/data/projects/staged"
fi

command -v make > /dev/null 2>&1 || {
    printf '%s\n' "make is required (run macos-habitat bootstrap first)" >&2
    exit 1
}

failures=0
ran=0
found_root=0

mtdt_files=""
for root in "${@}"; do
    [ -d "${root}" ] || continue
    found_root=1
    mtdt_files="${mtdt_files}$(
        find "${root}" \
            \( -name .git -o -name node_modules -o -name .venv -o -name venv \
            -o -name __pycache__ \) -prune \
            -o -iname .mtdt.yaml -print
    )
"
done

[ "${found_root}" -eq 1 ] || {
    printf 'Missing projects tree (tried: %s)\n' "${*}" >&2
    exit 1
}

while IFS= read -r mtdt; do
    [ -n "${mtdt}" ] || continue
    dir="$(CDPATH='' cd -- "$(dirname "${mtdt}")" && pwd)" || continue
    [ "${dir}" = "${self}" ] && continue

    makefile=""
    if [ -f "${dir}/Makefile" ]; then
        makefile="${dir}/Makefile"
    elif [ -f "${dir}/makefile" ]; then
        makefile="${dir}/makefile"
    else
        continue
    fi
    grep -q '^install[[:space:]]*:' "${makefile}" || continue

    printf '>>> make install: %s\n' "${dir}"
    ran=$((ran + 1))
    if make -C "${dir}" install; then
        :
    else
        printf '<<< failed: %s\n' "${dir}" >&2
        failures=$((failures + 1))
    fi
done << EOF
${mtdt_files}
EOF

if [ "${ran}" -eq 0 ]; then
    printf 'No checkouts with an install target\n' >&2
    exit 1
fi
if [ "${failures}" -gt 0 ]; then
    printf 'install-checkouts: %s failure(s) of %s\n' \
        "${failures}" "${ran}" >&2
    exit 1
fi

printf 'install-checkouts: %s checkout(s) ok\n' "${ran}"
