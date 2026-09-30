#!/bin/bash
# sign-themes.sh — builds themes/*/ and submits each to AMO's unlisted
# (self-distribution) channel for signing via web-ext; writes the signed
# XPIs to build/signed/<name>.xpi. Needs an AMO API key/secret (Manage API
# Keys on addons.mozilla.org) — not for publishing anywhere, only for the
# automated signature Firefox requires to sideload an add-on at all.
#
# Credentials: AMO_JWT_ISSUER / AMO_JWT_SECRET in the environment, or a
# local .amo-api-key file (never committed — see .gitignore) with:
#   AMO_JWT_ISSUER=user:1234:56
#   AMO_JWT_SECRET=...
set -eo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# shellcheck disable=SC1091
[[ -f .amo-api-key ]] && source .amo-api-key

if [[ -z "${AMO_JWT_ISSUER:-}" || -z "${AMO_JWT_SECRET:-}" ]]; then
    echo "sign-themes: set AMO_JWT_ISSUER and AMO_JWT_SECRET (env or .amo-api-key)" >&2
    exit 1
fi

out_dir="build/signed"
mkdir -p "$out_dir"

for dir in themes/*/; do
    name=$(basename "$dir")
    work="build/signed/.$name"
    rm -rf "$work"
    npx --yes web-ext sign \
        --source-dir "$dir" \
        --artifacts-dir "$work" \
        --api-key "$AMO_JWT_ISSUER" \
        --api-secret "$AMO_JWT_SECRET" \
        --channel unlisted
    signed=$(find "$work" -name '*.xpi' -print -quit)
    if [[ -z "$signed" ]]; then
        echo "sign-themes: no signed .xpi came back for $name" >&2
        exit 1
    fi
    install -m 0644 "$signed" "$out_dir/$name.xpi"
    rm -rf "$work"
    echo "sign-themes: $out_dir/$name.xpi"
done
