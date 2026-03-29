#!/bin/bash
# Tonado installation script for Raspberry Pi
# Usage: curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | sudo bash

set -euo pipefail

TONADO_DIR="/opt/tonado"
TONADO_USER="${SUDO_USER:-pi}"
MEDIA_DIR="/home/${TONADO_USER}/tonado/media"
CONFIG_DIR="/home/${TONADO_USER}/tonado/config"

echo "=== Tonado Installation ==="
echo "User: $TONADO_USER"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Bitte als root ausfuehren: sudo bash install.sh"
    exit 1
fi

NEEDS_REBOOT=false

echo "[1/9] System-Pakete installieren..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    mpd mpc \
    hostapd dnsmasq \
    nginx \
    git \
    i2c-tools spi-tools

echo "[2/9] Verzeichnisse erstellen..."
mkdir -p "$TONADO_DIR"
mkdir -p "$MEDIA_DIR" "$MEDIA_DIR/.playlists" "$CONFIG_DIR"
chown -R "$TONADO_USER:$TONADO_USER" "/home/${TONADO_USER}/tonado"

echo "[3/9] Tonado installieren..."
if [ -d "${TONADO_DIR}/.git" ]; then
    cd "$TONADO_DIR" && git pull
else
    git clone https://github.com/t13gazh/tonado.git "$TONADO_DIR"
fi

cd "$TONADO_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -e ".[pi]" -q

# Add user to hardware groups
usermod -aG audio,spi,i2c,gpio "$TONADO_USER" 2>/dev/null || true

echo "[4/9] HifiBerry MiniAmp konfigurieren..."
BOOT_CONFIG="/boot/firmware/config.txt"
[ ! -f "$BOOT_CONFIG" ] && BOOT_CONFIG="/boot/config.txt"

# Disable onboard audio, enable HifiBerry MiniAmp
if ! grep -q "dtoverlay=hifiberry-dac" "$BOOT_CONFIG"; then
    # Comment out onboard audio
    sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$BOOT_CONFIG"
    echo "" >> "$BOOT_CONFIG"
    echo "# Tonado: HifiBerry MiniAmp" >> "$BOOT_CONFIG"
    echo "dtoverlay=hifiberry-dac" >> "$BOOT_CONFIG"
    echo "gpio=25=op,dh" >> "$BOOT_CONFIG"
    echo "HINWEIS: HifiBerry MiniAmp Overlay hinzugefuegt."
    NEEDS_REBOOT=true
fi

echo "[5/9] MPD konfigurieren..."
cat > /etc/mpd.conf <<MPD
music_directory     "$MEDIA_DIR"
playlist_directory  "$MEDIA_DIR/.playlists"
db_file             "/var/lib/mpd/database"
log_file            "syslog"
pid_file            "/run/mpd/pid"
state_file          "/var/lib/mpd/state"
sticker_file        "/var/lib/mpd/sticker.sql"

bind_to_address     "localhost"
port                "6600"

auto_update         "yes"

audio_output {
    type            "alsa"
    name            "Tonado Audio"
    device          "default"
    mixer_type      "software"
}
MPD

chown -R mpd:audio /var/lib/mpd
systemctl enable mpd
systemctl restart mpd || true

echo "[6/9] Hardware-Interfaces pruefen..."

# Check for USB RFID reader (works without SPI/I2C)
USB_RFID=false
for hidraw in /dev/hidraw*; do
    [ -e "$hidraw" ] && USB_RFID=true && break
done

if [ "$USB_RFID" = true ]; then
    echo "  USB RFID-Reader erkannt — SPI/I2C fuer RFID nicht noetig."
else
    echo "  Kein USB RFID-Reader erkannt — SPI + I2C werden aktiviert."
fi

# Enable SPI (for RC522 RFID) — always enable, costs nothing
if grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
    echo "  SPI: bereits aktiviert."
elif grep -q "^#dtparam=spi=on" "$BOOT_CONFIG"; then
    sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$BOOT_CONFIG"
    echo "  SPI: aktiviert (war auskommentiert)."
    NEEDS_REBOOT=true
else
    echo "dtparam=spi=on" >> "$BOOT_CONFIG"
    echo "  SPI: aktiviert (hinzugefuegt)."
    NEEDS_REBOOT=true
fi

# Enable I2C (for PN532 RFID, MPU6050 gyro)
if grep -q "^dtparam=i2c_arm=on" "$BOOT_CONFIG"; then
    echo "  I2C: bereits aktiviert."
elif grep -q "^#dtparam=i2c_arm=on" "$BOOT_CONFIG"; then
    sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' "$BOOT_CONFIG"
    echo "  I2C: aktiviert (war auskommentiert)."
    NEEDS_REBOOT=true
else
    echo "dtparam=i2c_arm=on" >> "$BOOT_CONFIG"
    echo "  I2C: aktiviert (hinzugefuegt)."
    NEEDS_REBOOT=true
fi

# Verify kernel modules can be loaded (if no reboot needed)
if [ "$NEEDS_REBOOT" = false ]; then
    modprobe spidev 2>/dev/null && echo "  SPI-Modul: geladen." || true
    modprobe i2c-dev 2>/dev/null && echo "  I2C-Modul: geladen." || true
fi

echo "[7/9] systemd-Service installieren..."
cat > /etc/systemd/system/tonado.service <<SERVICE
[Unit]
Description=Tonado Music Box
After=network.target mpd.service
Wants=mpd.service

[Service]
Type=simple
User=$TONADO_USER
Group=$TONADO_USER
WorkingDirectory=$TONADO_DIR
ExecStart=$TONADO_DIR/.venv/bin/uvicorn core.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5
Environment=TONADO_DB_PATH=$CONFIG_DIR/tonado.db
Environment=TONADO_MEDIA_DIR=$MEDIA_DIR
Environment=TONADO_HARDWARE_MODE=auto

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable tonado.service
systemctl start tonado.service || true

echo "[8/9] Frontend pruefen..."
# Frontend is built on the dev machine and deployed via scp.
# Node.js is NOT installed on the Pi to save disk space (~500 MB).
# Build locally: cd web && npm run build
# Deploy: scp -r web/build/ pi@<ip>:/opt/tonado/web/build/
if [ -d "$TONADO_DIR/web/build" ] && [ -f "$TONADO_DIR/web/build/index.html" ]; then
    echo "  Frontend-Build gefunden."
else
    echo "  HINWEIS: Kein Frontend-Build gefunden!"
    echo "  Auf dem Entwicklungs-PC ausfuehren:"
    echo "    cd web && npm run build"
    echo "    scp -r web/build/ ${TONADO_USER}@$(hostname -I | awk '{print $1}'):/opt/tonado/web/build/"
fi
chown -R "$TONADO_USER:$TONADO_USER" "$TONADO_DIR"

echo "[9/9] Nginx Reverse Proxy konfigurieren..."
cat > /etc/nginx/sites-available/tonado <<'NGINX'
server {
    listen 80 default_server;
    server_name _;

    # Static frontend (built files)
    root /opt/tonado/web/build;
    index index.html;

    # API and WebSocket proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/tonado /etc/nginx/sites-enabled/tonado
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Tonado laeuft auf http://${IP}"
echo "(API auf Port 8080, Nginx auf Port 80)"

if [ "$NEEDS_REBOOT" = true ]; then
    echo ""
    echo "WICHTIG: Hardware-Konfiguration geaendert (SPI/I2C/Audio)."
    echo "Neustart erforderlich:"
    echo "  sudo reboot"
fi
echo ""
