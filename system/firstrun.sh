#!/bin/bash
# Tonado first-boot initialisation script.
#
# Runs exactly once on the very first boot of a freshly flashed image.
# Subsequent boots short-circuit via the marker file and do nothing.
#
# Responsibilities:
#   - Rotate SSH host keys (image ships with empty /etc/ssh so every
#     device gets unique keys instead of sharing the pi-gen chroot keys).
#   - Release the WiFi rfkill soft-block so the setup AP can come up on
#     the very first boot (runtime guard — see the rfkill section below).
#   - Configure Git so the system-side update flow can operate on the
#     repo without owner-mismatch complaints.
#   - Write the marker file so we never run again.
#
# This script is invoked by firstrun.service (oneshot, RemainAfterExit)
# before tonado-ap.service and tonado.service. Keep the logic minimal —
# anything that needs network must happen elsewhere.

set -euo pipefail

FIRSTRUN_MARKER="/var/lib/tonado/firstrun.done"
TONADO_USER="pi"
TONADO_GROUP="pi"
REPO_DIR="/opt/tonado"

# Idempotent guard: if the marker already exists, we already ran once.
if [ -f "${FIRSTRUN_MARKER}" ]; then
    exit 0
fi

# --- WiFi rfkill soft-block release ---
# A freshly flashed image has no WiFi regulatory domain set at runtime, so
# wlan0 comes up rfkill-soft-blocked and hostapd refuses to start — the
# setup AP never appears and a headless box is unreachable.
#
# The persistent country code lives in the bake (chroot) via
# `raspi-config nonint do_wifi_country DE` and is NOT our responsibility.
# But `iw reg set` is not reboot-persistent and the baked value may only
# take effect once the radio is actually unblocked, so we release the
# soft-block at runtime here, before tonado-ap.service starts hostapd.
# firstrun.service orders itself Before=tonado-ap.service, which in turn
# calls setup-ap.sh — so this guard always wins the race.
#
# Both tools are best-effort: on a dev box (or a minimal image) they may be
# absent, hence the `|| true`. `iw reg set DE` is a belt-and-braces double
# safeguard in case unblock alone leaves the domain at the world-roaming
# default "00".
rfkill unblock wifi 2>/dev/null || true
iw reg set DE 2>/dev/null || true

# --- SSH host keys ---
# The image is baked with the keys from the pi-gen chroot. Leaving them in
# place would mean every flashed device shares the same SSH identity — a
# trivial MITM vector. Regenerate unconditionally.
#
# Belt-and-braces: stop ssh.service during the rm/keygen window so no sshd
# instance can accept a connection with the old (or a half-written new)
# host key. Errors swallowed — on a dev box systemctl might be absent.
if [ -d /etc/ssh ]; then
    systemctl stop ssh.service 2>/dev/null || true
    systemctl stop sshd.service 2>/dev/null || true
    rm -f /etc/ssh/ssh_host_*
    ssh-keygen -A
    # Bring ssh back up so the first boot still accepts logins.
    systemctl start ssh.service 2>/dev/null || true
fi

# --- JWT secret: intentionally NOT handled here ---
# A previous version wrote /opt/tonado/config/jwt_secret here. That file was
# dead: AuthService.start() reads/generates auth.jwt_secret from the SQLite
# config (ConfigService), never from a file — verified against
# core/services/auth_service.py. Writing it produced false confidence about
# a secret that is never consumed, so the block was removed. The per-device
# secret is generated on first AuthService start and persisted in the DB.

# --- Git trust configuration ---
# The repo is baked into the image as the pi-gen chroot user, but runs
# as pi at runtime. Without this setting, `git fetch` during updates
# trips "fatal: detected dubious ownership" and the update flow breaks.
# Identity is set because some git operations refuse to run without one,
# even though we never commit from the device itself.
#
# firstrun.service runs as root, so a plain `git config --global ...`
# would land in /root/.gitconfig and never be picked up by the pi-user
# update flow. Write the config file directly, then chown so pi owns it.
if [ -d "${REPO_DIR}/.git" ]; then
    PI_HOME="/home/${TONADO_USER}"
    GITCONFIG="${PI_HOME}/.gitconfig"
    if [ -d "${PI_HOME}" ]; then
        # Append-or-create, idempotent: only write if the section is missing.
        if [ ! -f "${GITCONFIG}" ] || ! grep -q "^\[safe\]" "${GITCONFIG}" 2>/dev/null; then
            cat >> "${GITCONFIG}" <<EOF
[safe]
	directory = ${REPO_DIR}
[user]
	email = tonado@localhost
	name = Tonado
EOF
        fi
        chown "${TONADO_USER}:${TONADO_GROUP}" "${GITCONFIG}"
        chmod 644 "${GITCONFIG}"
    fi
fi

# --- Marker ---
# Write ISO8601 timestamp for debugging. Presence alone is what matters.
mkdir -p "$(dirname "${FIRSTRUN_MARKER}")"
date -Iseconds > "${FIRSTRUN_MARKER}"

exit 0
