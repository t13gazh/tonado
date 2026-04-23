#!/bin/bash
# Tonado Imager WiFi probe.
#
# Runs on every boot before tonado-ap.service. Waits up to 20 seconds for
# NetworkManager to bring up a home WiFi connection (typically the one
# the Raspberry Pi Imager seeded into the image during flashing, but
# works equally well for anything else the user configured).
#
# Outcome is communicated via a single flag file:
#   /run/tonado/home-wifi-active  -> present  => home WiFi is up
#                                 -> absent   => no home WiFi, start AP
#
# tonado-ap.service carries a `ConditionPathExists=!/run/tonado/home-wifi-active`
# so an active home WiFi suppresses the setup AP. /run is a tmpfs, so the
# flag vanishes on every reboot and this probe re-evaluates from scratch.
#
# This script intentionally always exits 0 — a non-zero return would make
# systemd mark the unit "failed" and cascade, but the absence of the flag
# file is already the clean "no home WiFi" signal we need.

set -euo pipefail

FLAG_DIR="/run/tonado"
FLAG_FILE="${FLAG_DIR}/home-wifi-active"
PROBE_TIMEOUT=20  # seconds
PROBE_INTERVAL=1  # seconds

mkdir -p "${FLAG_DIR}"
# Ensure a stale flag from an older boot cycle (shouldn't happen on tmpfs,
# but belt and braces) doesn't pre-approve us.
rm -f "${FLAG_FILE}"

is_connected() {
    # Treat a WiFi connection as "up" only if we have both an SSID and
    # an IPv4 address on wlan0. `iwgetid -r` gives us the SSID; an empty
    # result means either no association or wlan0 down. `hostname -I`
    # returns space-separated addresses — non-empty means DHCP succeeded.
    local ssid
    local addrs
    ssid="$(iwgetid -r 2>/dev/null || true)"
    if [ -z "${ssid}" ]; then
        return 1
    fi
    addrs="$(hostname -I 2>/dev/null || true)"
    if [ -z "${addrs}" ]; then
        return 1
    fi
    return 0
}

# Poll for up to PROBE_TIMEOUT seconds. Bail out as soon as we're connected.
for _ in $(seq 1 "${PROBE_TIMEOUT}"); do
    if is_connected; then
        touch "${FLAG_FILE}"
        exit 0
    fi
    sleep "${PROBE_INTERVAL}"
done

# Timed out without a home WiFi connection. Leave the flag absent so the
# AP service will start, but do not fail — the AP service's own condition
# handles the decision from here.
exit 0
