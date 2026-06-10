#!/bin/bash
# Tonado Access Point control — the single privileged mechanism for bringing
# wlan0 up as an AP and handing it back to NetworkManager.
#
# Two AP flavours share this one script:
#   - setup    (first boot): OPEN AP, started by tonado-ap.service at boot.
#                Parents have no credentials yet, so the network is open.
#   - recovery (runtime):    WPA2 AP, started by CaptivePortalService via
#                `sudo -n` when the box loses its known WiFi. SSID + PSK are
#                the values the parents chose in the setup wizard.
#
# wlan0 is taken away from NetworkManager only while the AP is up, and handed
# back on stop — there is deliberately NO static unmanaged drop-in. This keeps
# the home-WiFi probe / imager path working without a chicken-and-egg deadlock.
#
# Usage:
#   setup-ap.sh start open [ssid]
#   setup-ap.sh start secured <ssid> <psk>
#   setup-ap.sh stop

set -euo pipefail

AP_IP="192.168.4.1"
AP_RANGE_START="192.168.4.2"
AP_RANGE_END="192.168.4.20"
COUNTRY_CODE="DE"
DEFAULT_SSID="Tonado-Setup"

# /run is tmpfs — configs never hit the SD card and vanish on reboot.
RUN_DIR="/run/tonado"
HOSTAPD_CONF="${RUN_DIR}/hostapd.conf"
DNSMASQ_CONF="${RUN_DIR}/dnsmasq.conf"

start_ap() {
    local mode="${1:-open}"
    local ssid="${2:-${DEFAULT_SSID}}"
    local psk="${3:-}"

    if [ "$mode" != "open" ] && [ "$mode" != "secured" ]; then
        echo "setup-ap.sh: unknown mode '${mode}' (expected open|secured)" >&2
        exit 1
    fi
    if [ "$mode" = "secured" ] && [ -z "$psk" ]; then
        echo "setup-ap.sh: secured mode requires a PSK" >&2
        exit 1
    fi

    echo "Starting Tonado AP (mode=${mode}, ssid=${ssid})..."

    mkdir -p "${RUN_DIR}"

    # Take wlan0 away from NetworkManager for the lifetime of the AP only.
    nmcli device set wlan0 managed no 2>/dev/null || true

    # Configure wlan0 with a static IP.
    ip addr flush dev wlan0
    ip addr add "${AP_IP}/24" dev wlan0
    ip link set wlan0 up

    # Base hostapd config (open). country_code is mandatory — without a
    # regulatory domain the radio stays rfkill-soft-blocked and hostapd
    # refuses to start.
    cat > "${HOSTAPD_CONF}" <<HOSTAPD
interface=wlan0
driver=nl80211
ssid=${ssid}
country_code=${COUNTRY_CODE}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
HOSTAPD

    if [ "$mode" = "secured" ]; then
        cat >> "${HOSTAPD_CONF}" <<HOSTAPD
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=${psk}
HOSTAPD
    fi

    # dnsmasq: DHCP for clients + catch-all DNS redirect to the portal IP.
    cat > "${DNSMASQ_CONF}" <<DNSMASQ
interface=wlan0
bind-interfaces
dhcp-range=${AP_RANGE_START},${AP_RANGE_END},255.255.255.0,24h
address=/#/${AP_IP}
DNSMASQ

    hostapd -B "${HOSTAPD_CONF}"
    dnsmasq -C "${DNSMASQ_CONF}"

    echo "AP started: SSID='${ssid}', IP=${AP_IP}"
}

stop_ap() {
    echo "Stopping Tonado AP..."

    pkill -f "hostapd.*tonado" 2>/dev/null || true
    pkill -f "dnsmasq.*tonado" 2>/dev/null || true

    rm -f "${HOSTAPD_CONF}" "${DNSMASQ_CONF}"
    ip addr flush dev wlan0 2>/dev/null || true

    # Hand wlan0 back to NetworkManager so a home-WiFi connection can use it.
    nmcli device set wlan0 managed yes 2>/dev/null || true

    echo "AP stopped."
}

case "${1:-}" in
    start) shift; start_ap "$@" ;;
    stop)  stop_ap ;;
    *)     echo "Usage: $0 {start open [ssid]|start secured <ssid> <psk>|stop}" >&2; exit 1 ;;
esac
