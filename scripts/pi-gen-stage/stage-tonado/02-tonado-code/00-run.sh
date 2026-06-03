#!/bin/bash -e
# Stage 02: clone Tonado repo and install Python dependencies
# Runs INSIDE the chroot (qemu-arm-static). git is installed via 00-packages.
#
# Required env (exported by pi-gen config):
#   TONADO_VERSION       -- git tag to check out, e.g. "v0.3.1-beta".
#                           NOT prefixed with "v" here; the prefix is added
#                           below so the config can use either "v0.3.1-beta"
#                           or "0.3.1-beta".
#   TONADO_REPO          -- optional, defaults to the public GitHub repo.
#   TONADO_EXPECTED_SHA  -- optional, pins the commit HEAD that the tag
#                           resolves to. If set, a mismatch fails the build
#                           (fail-fast, SUPPLY-CHAIN INTEGRITY). If unset,
#                           a warning is printed (transitional period until
#                           the release process produces signed tags).

set -euo pipefail

: "${TONADO_VERSION:?TONADO_VERSION must be set in pi-gen config}"
: "${TONADO_REPO:=https://github.com/t13gazh/tonado.git}"
: "${TONADO_EXPECTED_SHA:=}"

# Strip a leading "v" if present, then re-add it for the git ref -- lets the
# caller write either form without ambiguity.
TONADO_TAG="${TONADO_VERSION#v}"
TONADO_TAG="v${TONADO_TAG}"

install -d -o 1000 -g 1000 "${ROOTFS_DIR}/opt"

on_chroot << EOF
set -euo pipefail
cd /opt
# Clone pinned tag only (shallow-ish but with tag metadata so SystemService.apply_update
# can still fetch newer commits later). --no-single-branch keeps the default branch
# reachable for future 'git pull' in the app's self-update path.
git clone --branch "${TONADO_TAG}" "${TONADO_REPO}" /opt/tonado
cd /opt/tonado

# --- Supply-chain integrity: verify the checked-out commit ---
# Release tags are NOT GPG-signed yet (checked via 'git tag -v v0.3.1-beta' on
# the host: "error: no signature found"). Until the release process signs tags,
# fall back to an explicit commit-SHA pin set by the pi-gen config.
# Upgrade path: once tags are signed, replace this with 'git verify-tag'.
ACTUAL_SHA="\$(git rev-parse HEAD)"
if [ -n "${TONADO_EXPECTED_SHA}" ]; then
    if [ "\${ACTUAL_SHA}" != "${TONADO_EXPECTED_SHA}" ]; then
        echo "ERROR: Tag ${TONADO_TAG} resolved to \${ACTUAL_SHA}" >&2
        echo "       but TONADO_EXPECTED_SHA is ${TONADO_EXPECTED_SHA}." >&2
        echo "       Refusing to build -- tag may have been force-pushed." >&2
        exit 1
    fi
    echo "OK: Commit SHA matches TONADO_EXPECTED_SHA (\${ACTUAL_SHA})."
else
    echo "WARNING: TONADO_EXPECTED_SHA not set. Skipping commit-SHA pin." >&2
    echo "         Set TONADO_EXPECTED_SHA in pi-gen config for reproducible builds." >&2
    echo "         Tag ${TONADO_TAG} currently resolves to \${ACTUAL_SHA}." >&2
fi

# Allow Git to operate on /opt/tonado for the pi user (runtime self-update path).
# Writing directly to /home/pi/.gitconfig avoids 'git config --global' landing
# in /root/.gitconfig when the chroot hook runs as root.
install -d -o pi -g pi -m 755 /home/pi
cat > /home/pi/.gitconfig <<'GITCFG'
[safe]
	directory = /opt/tonado
GITCFG
chown pi:pi /home/pi/.gitconfig
chmod 644 /home/pi/.gitconfig

# Python venv with runtime + Pi-hardware extras.
python3 -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install --quiet -e ".[pi]"

# Frontend: web/build/ is committed in the repo, no npm step needed.
# Sanity-check that the committed build exists; fail loudly if not.
if [ ! -f web/build/index.html ]; then
    echo "ERROR: web/build/index.html missing in tag ${TONADO_TAG}." >&2
    echo "  Release checklist: build frontend, commit web/build/, re-tag." >&2
    exit 1
fi
EOF
