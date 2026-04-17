#!/bin/bash
# Tonado uninstall script — removes Tonado completely for re-testing the installer.
# Usage: sudo bash /opt/tonado/system/uninstall.sh
# Or:    ssh pi@tonado-dev.local "sudo bash /opt/tonado/system/uninstall.sh"

set -euo pipefail

TONADO_DIR="/opt/tonado"
TONADO_USER="${SUDO_USER:-pi}"
MEDIA_DIR="/home/${TONADO_USER}/tonado"

if [ "$(id -u)" -ne 0 ]; then
    echo "Bitte als root ausführen: sudo bash uninstall.sh"
    exit 1
fi

echo "=== Tonado Deinstallation ==="
echo ""
echo "Folgendes wird entfernt:"
echo "  - Tonado Service + Code (/opt/tonado)"
echo "  - Nginx Tonado-Config"
echo "  - MPD-Konfiguration (wird auf Default zurückgesetzt)"
echo "  - Tonado systemd-Service"
echo "  - Tonado journald-Config"
echo ""
echo "NICHT entfernt:"
echo "  - Medien-Dateien ($MEDIA_DIR/media/)"
echo "  - System-Pakete (python3, mpd, nginx, etc.)"
echo "  - Hardware-Interfaces (SPI/I2C bleiben aktiviert)"
echo ""

# Give 5s to abort
echo "Deinstallation startet in 5 Sekunden... (Ctrl+C zum Abbrechen)"
sleep 5

echo "[1/6] Tonado-Service stoppen..."
systemctl stop tonado.service 2>/dev/null || true
systemctl disable tonado.service 2>/dev/null || true
rm -f /etc/systemd/system/tonado.service
systemctl daemon-reload

echo "[2/6] Captive Portal stoppen..."
# Stop hostapd/dnsmasq if running as captive portal
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

echo "[3/6] Nginx-Config entfernen..."
rm -f /etc/nginx/sites-enabled/tonado
rm -f /etc/nginx/sites-available/tonado
# Restore default Nginx config
ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default 2>/dev/null || true
nginx -t 2>/dev/null && systemctl restart nginx || true

echo "[4/6] MPD auf Default zurücksetzen..."
if [ -f /etc/mpd.conf.dpkg-dist ]; then
    cp /etc/mpd.conf.dpkg-dist /etc/mpd.conf
elif [ -f /etc/mpd.conf ]; then
    # Reset to minimal default
    cat > /etc/mpd.conf <<'MPD'
music_directory     "/var/lib/mpd/music"
playlist_directory  "/var/lib/mpd/playlists"
db_file             "/var/lib/mpd/database"
log_file            "syslog"
pid_file            "/run/mpd/pid"
state_file          "/var/lib/mpd/state"
sticker_file        "/var/lib/mpd/sticker.sql"
bind_to_address     "localhost"
MPD
fi
systemctl restart mpd 2>/dev/null || true

echo "[5/6] Tonado-Code entfernen..."
rm -rf "$TONADO_DIR"

echo "[6/6] Tonado-Config entfernen..."
# Remove config DB but keep media files
rm -rf "$MEDIA_DIR/config"
rm -f /etc/systemd/journald.conf.d/tonado.conf 2>/dev/null || true
systemctl restart systemd-journald 2>/dev/null || true

# Remove install marker so a subsequent install.sh runs from scratch.
rm -rf /var/lib/tonado

echo ""
echo "=== Deinstallation abgeschlossen ==="
echo ""
echo "Medien-Dateien sind erhalten: $MEDIA_DIR/media/"
echo "Um alles zu entfernen: rm -rf $MEDIA_DIR"
echo ""
echo "Tonado kann jetzt neu installiert werden:"
echo "  curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | sudo bash"
echo ""
