#!/bin/bash
# Tonado Setup Access Point control script
# Starts/stops a temporary WiFi AP for first-boot configuration.

set -euo pipefail

AP_SSID="Tonado-Setup"
AP_IP="192.168.4.1"
AP_RANGE_START="192.168.4.2"
AP_RANGE_END="192.168.4.20"
HOSTAPD_CONF="/tmp/tonado-hostapd.conf"
DNSMASQ_CONF="/tmp/tonado-dnsmasq.conf"

start_ap() {
    echo "Starting Tonado Setup AP..."

    # Stop NetworkManager from managing wlan0
    nmcli device set wlan0 managed no 2>/dev/null || true

    # Configure wlan0 with static IP
    ip addr flush dev wlan0
    ip addr add "${AP_IP}/24" dev wlan0
    ip link set wlan0 up

    # Write hostapd config
    cat > "$HOSTAPD_CONF" <<HOSTAPD
interface=wlan0
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
HOSTAPD

    # Write dnsmasq config (DHCP + DNS redirect to AP)
    cat > "$DNSMASQ_CONF" <<DNSMASQ
interface=wlan0
bind-interfaces
dhcp-range=${AP_RANGE_START},${AP_RANGE_END},255.255.255.0,24h
address=/#/${AP_IP}
DNSMASQ

    # Start services
    hostapd -B "$HOSTAPD_CONF"
    dnsmasq -C "$DNSMASQ_CONF"

    echo "Setup AP started: SSID='${AP_SSID}', IP=${AP_IP}"
    echo "Open http://${AP_IP}:8080 to configure Tonado."
}

stop_ap() {
    echo "Stopping Tonado Setup AP..."

    # Kill hostapd and dnsmasq
    pkill -f "hostapd.*tonado" 2>/dev/null || true
    pkill -f "dnsmasq.*tonado" 2>/dev/null || true

    # Clean up
    rm -f "$HOSTAPD_CONF" "$DNSMASQ_CONF"
    ip addr flush dev wlan0

    # Restore NetworkManager
    nmcli device set wlan0 managed yes 2>/dev/null || true

    echo "Setup AP stopped."
}

case "${1:-}" in
    start)  start_ap ;;
    stop)   stop_ap ;;
    *)      echo "Usage: $0 {start|stop}" >&2; exit 1 ;;
esac
