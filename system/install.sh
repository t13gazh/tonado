#!/bin/bash
# Tonado installation script for Raspberry Pi
# Usage: curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | bash

set -euo pipefail

TONADO_DIR="/opt/tonado"
TONADO_USER="tonado"
MEDIA_DIR="/home/${TONADO_USER}/media"

echo "=== Tonado Installation ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Bitte als root ausfuehren: sudo bash install.sh"
    exit 1
fi

# Check if running on a Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "WARNUNG: Kein Raspberry Pi erkannt. Installation wird trotzdem fortgesetzt."
fi

echo "[1/7] System-Pakete installieren..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    mpd mpc \
    hostapd dnsmasq \
    nginx \
    git \
    i2c-tools spi-tools

echo "[2/7] Benutzer erstellen..."
if ! id "$TONADO_USER" &>/dev/null; then
    useradd -r -m -s /bin/bash -G audio,spi,i2c,gpio "$TONADO_USER"
fi

echo "[3/7] Verzeichnisse erstellen..."
mkdir -p "$TONADO_DIR"/{config,logs}
mkdir -p "$MEDIA_DIR"
chown -R "$TONADO_USER:$TONADO_USER" "$TONADO_DIR" "$MEDIA_DIR"

echo "[4/7] Tonado installieren..."
if [ -d "${TONADO_DIR}/.git" ]; then
    cd "$TONADO_DIR" && git pull
else
    git clone https://github.com/t13gazh/tonado.git "$TONADO_DIR"
fi

cd "$TONADO_DIR"
python3 -m venv .venv
.venv/bin/pip install -e ".[pi]"

echo "[5/7] MPD konfigurieren..."
cat > /etc/mpd.conf <<'MPD'
music_directory     "/home/tonado/media"
playlist_directory  "/home/tonado/media/.playlists"
db_file             "/var/lib/mpd/database"
log_file            "/var/log/mpd/mpd.log"
pid_file            "/run/mpd/pid"
state_file          "/var/lib/mpd/state"
sticker_file        "/var/lib/mpd/sticker.sql"

bind_to_address     "localhost"
port                "6600"

audio_output {
    type        "alsa"
    name        "Tonado Audio"
    mixer_type  "software"
}
MPD

mkdir -p "$MEDIA_DIR/.playlists"
chown -R mpd:audio /var/lib/mpd
systemctl restart mpd

echo "[6/7] Hardware-Interfaces aktivieren..."
# Enable SPI
raspi-config nonint do_spi 0 2>/dev/null || true
# Enable I2C
raspi-config nonint do_i2c 0 2>/dev/null || true

echo "[7/7] systemd-Services installieren..."
cp "$TONADO_DIR/system/tonado.service" /etc/systemd/system/
cp "$TONADO_DIR/system/tonado-ap.service" /etc/systemd/system/
chmod +x "$TONADO_DIR/system/setup-ap.sh"

systemctl daemon-reload
systemctl enable tonado.service
systemctl enable tonado-ap.service
systemctl start tonado.service

echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Tonado laeuft auf http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "Falls kein WiFi konfiguriert ist, verbinde dich mit dem"
echo "WLAN 'Tonado-Setup' und oeffne http://192.168.4.1:8080"
echo ""
