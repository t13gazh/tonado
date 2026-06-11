#!/bin/bash
# Tonado Imager WiFi probe.
#
# Runs on every boot before tonado-ap.service. Waits up to 30 seconds for
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
# Additionally, this probe produces a one-shot WiFi scan cache the setup wizard
# consumes, written BEFORE the AP grabs wlan0:
#   /run/tonado/wifi-scan.json
# This unit runs `After=NetworkManager.service Before=tonado-ap.service`, i.e.
# while wlan0 is still NM-managed — the ONLY window in which `nmcli device wifi
# list` works. Once tonado-ap.service hands wlan0 to hostapd, no scan is
# possible until the AP is torn down. The cache lets the wizard show nearby
# networks without re-scanning (which it cannot do while serving over the AP).
#
# This script intentionally always exits 0 — a non-zero return would make
# systemd mark the unit "failed" and cascade, but the absence of the flag
# file is already the clean "no home WiFi" signal we need.

set -euo pipefail

FLAG_DIR="/run/tonado"
FLAG_FILE="${FLAG_DIR}/home-wifi-active"
SCAN_FILE="${FLAG_DIR}/wifi-scan.json"
SCAN_TIMEOUT=8    # seconds — hard cap so a hung scan can never delay the AP.
PROBE_TIMEOUT=30  # seconds — generous: without network-online.target this may
                  # start before NM has finished associating the imager-seeded
                  # connection on a cold boot.
PROBE_INTERVAL=1  # seconds

mkdir -p "${FLAG_DIR}"
# Ensure a stale flag from an older boot cycle (shouldn't happen on tmpfs,
# but belt and braces) doesn't pre-approve us.
rm -f "${FLAG_FILE}"

# ---------------------------------------------------------------------------
# WiFi scan cache (strictly additive, strictly BEFORE the is_connected poll).
# ---------------------------------------------------------------------------
# Emits /run/tonado/wifi-scan.json per the wizard contract:
#   {"scanned_at": <epoch_int>, "networks": [
#       {"ssid": str, "signal": 0..100, "security": "wpa2"|"wpa"|"wep"|"open"}
#   ]}
# Always writes a file (even on scan failure -> empty networks list) so the
# wizard can distinguish "scanned, nothing nearby" from "never scanned". The
# whole block is best-effort: any failure leaves an empty-but-valid cache and
# falls through to the unchanged poll. Never aborts the script.

# JSON-escape a raw string for embedding in a double-quoted JSON value.
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"   # backslash first
    s="${s//\"/\\\"}"   # double quote
    s="${s//$'\t'/\\t}" # tab
    s="${s//$'\n'/\\n}" # newline (defensive; SSIDs shouldn't contain one)
    s="${s//$'\r'/\\r}"
    # Escape every REMAINING control char (U+0000..U+001F) as \uXXXX so strict
    # JSON parsers never see a raw control byte. \t \n \r were already turned into
    # two-char "\t"/"\n"/"\r" sequences above and are skipped here; the rest are
    # mapped one byte at a time. This also guarantees the \x01/\x02 split
    # sentinels can never leak into the output even if a restore step were ever
    # missed. We use explicit per-byte substitutions rather than a `[...]` range
    # glob because bracket-range matching of control bytes is collation-dependent
    # and silently misses bytes like 0x07 in some locales (verified empirically).
    local code
    for code in 0 1 2 3 4 5 6 7 8 11 12 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31; do
        # 9=\t, 10=\n, 13=\r already handled above and intentionally omitted.
        local raw esc
        printf -v raw '\\x%02x' "${code}"   # e.g. "\x07" as a 4-char literal
        raw="$(printf "${raw}")"            # turn it into the actual control byte
        printf -v esc '\\u%04x' "${code}"   # e.g. ""
        s="${s//"${raw}"/${esc}}"
    done
    printf '%s' "${s}"
}

# Map nmcli SECURITY flags (e.g. "WPA2", "WPA1 WPA2", "WEP", "" => open) to the
# contract's single token. Prefer the strongest indicated scheme.
map_security() {
    local sec="$1"
    if [ -z "${sec}" ] || [ "${sec}" = "--" ]; then
        printf 'open'
    elif printf '%s' "${sec}" | grep -qi 'WPA2\|WPA3\|RSN'; then
        printf 'wpa2'
    elif printf '%s' "${sec}" | grep -qi 'WPA'; then
        printf 'wpa'
    elif printf '%s' "${sec}" | grep -qi 'WEP'; then
        printf 'wep'
    else
        printf 'open'
    fi
}

write_scan_cache() {
    local scanned_at
    scanned_at="$(date +%s)"

    # Run the scan under a hard timeout. nmcli's -t (terse) mode escapes field
    # separators inside values as '\:', so a colon in an SSID arrives as '\:'.
    # --rescan yes forces a fresh scan rather than returning a stale cache.
    local raw=""
    raw="$(timeout "${SCAN_TIMEOUT}" \
        nmcli -t -f SSID,SIGNAL,SECURITY device wifi list --rescan yes \
        2>/dev/null || true)"

    # Build the networks array. Dedupe by SSID (first/strongest wins — nmcli
    # already orders strongest-first), skip hidden/empty SSIDs.
    local networks=""
    local seen_ssids=$'\n'
    local line
    while IFS= read -r line; do
        [ -z "${line}" ] && continue

        # Split on UNescaped colons. nmcli escapes literal colons inside a value
        # as '\:', so temporarily swap that PAIR to a sentinel, split on the real
        # field-separator colons, then restore. The pattern must match the '\:'
        # pair literally: a character class '[\\]:' does this, whereas the naive
        # '\\:' in bash pattern substitution matches a BARE ':' and would mangle
        # every separator (verified empirically). nmcli also escapes a literal
        # backslash as '\\', so first protect '\\' too.
        local tmp="${line//[\\][\\]/$'\x02'}"  # protect escaped backslash pair
        tmp="${tmp//[\\]:/$'\x01'}"            # protect escaped colon pair
        local ssid_raw="${tmp%%:*}"
        local rest="${tmp#*:}"
        local signal_raw="${rest%%:*}"
        local security_raw="${rest#*:}"
        # Restore: sentinel \x01 -> ':' (literal colon), \x02 -> '\' (literal
        # backslash). The backslash replacement goes through a $bs variable
        # because a literal '\\}' inside a quoted ${var//.../...} is a bash
        # parse error. Order is irrelevant; the two sentinels are distinct.
        local bs='\'
        ssid_raw="${ssid_raw//$'\x01'/:}"
        ssid_raw="${ssid_raw//$'\x02'/${bs}}"
        security_raw="${security_raw//$'\x01'/:}"
        security_raw="${security_raw//$'\x02'/${bs}}"

        # Skip hidden networks (empty SSID) — unusable in the wizard.
        [ -z "${ssid_raw}" ] && continue

        # Dedupe by SSID.
        case "${seen_ssids}" in
            *$'\n'"${ssid_raw}"$'\n'*) continue ;;
        esac
        seen_ssids="${seen_ssids}${ssid_raw}"$'\n'

        # Clamp signal to 0..100 integers; default 0 on garbage.
        local signal=0
        if printf '%s' "${signal_raw}" | grep -qE '^[0-9]+$'; then
            signal="${signal_raw}"
            [ "${signal}" -gt 100 ] && signal=100
        fi

        local security
        security="$(map_security "${security_raw}")"

        local ssid_json
        ssid_json="$(json_escape "${ssid_raw}")"

        if [ -n "${networks}" ]; then
            networks="${networks},"
        fi
        networks="${networks}{\"ssid\":\"${ssid_json}\",\"signal\":${signal},\"security\":\"${security}\"}"
    done <<< "${raw}"

    # Atomic write: tempfile in the same dir + mv (rename is atomic on tmpfs).
    local tmpfile
    tmpfile="$(mktemp "${SCAN_FILE}.XXXXXX")" || return 0
    printf '{"scanned_at":%s,"networks":[%s]}\n' "${scanned_at}" "${networks}" \
        > "${tmpfile}" 2>/dev/null || { rm -f "${tmpfile}"; return 0; }
    mv -f "${tmpfile}" "${SCAN_FILE}" 2>/dev/null || { rm -f "${tmpfile}"; return 0; }
    return 0
}

# Never let a scan failure abort the probe (set -e is active).
write_scan_cache || true

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
