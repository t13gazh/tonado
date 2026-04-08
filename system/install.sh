#!/bin/bash
# Tonado installation script for Raspberry Pi
# Usage: curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | sudo bash

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

TONADO_DIR="/opt/tonado"
TONADO_USER="${SUDO_USER:-pi}"
MEDIA_DIR="/home/${TONADO_USER}/tonado/media"
CONFIG_DIR="/home/${TONADO_USER}/tonado/config"

echo "=== Tonado Installation ==="
echo "User: $TONADO_USER"
echo ""

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "Bitte als root ausführen: sudo bash install.sh"
    exit 1
fi

# Check if user exists
if ! id "$TONADO_USER" &>/dev/null; then
    echo "FEHLER: Benutzer '$TONADO_USER' existiert nicht."
    echo "Bitte im Raspberry Pi Imager den Benutzernamen 'pi' setzen."
    exit 1
fi

# Detect Pi model (warn if not a Pi, but continue)
PI_MODEL="unbekannt"
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
    echo "Pi-Modell: $PI_MODEL"
else
    echo "HINWEIS: Kein Raspberry Pi erkannt — Installation wird fortgesetzt (Test-Modus)."
fi

NEEDS_REBOOT=false

echo "[1/11] System-Pakete installieren..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    mpd mpc \
    hostapd dnsmasq \
    nginx \
    git \
    i2c-tools spi-tools \
    avahi-daemon

echo "[2/11] Verzeichnisse erstellen..."
mkdir -p "$TONADO_DIR"
mkdir -p "$MEDIA_DIR" "$MEDIA_DIR/.playlists" "$CONFIG_DIR"
chown -R "$TONADO_USER:$TONADO_USER" "/home/${TONADO_USER}/tonado"

echo "[3/11] Tonado installieren..."
if [ -d "${TONADO_DIR}/.git" ]; then
    cd "$TONADO_DIR"
    git fetch origin main
    git reset --hard origin/main
else
    git clone https://github.com/t13gazh/tonado.git "$TONADO_DIR"
fi

cd "$TONADO_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -e ".[pi]" -q

# Add user to hardware groups
usermod -aG audio,spi,i2c,gpio "$TONADO_USER" 2>/dev/null || true

echo "[4/11] Audio konfigurieren..."
BOOT_CONFIG="/boot/firmware/config.txt"
[ ! -f "$BOOT_CONFIG" ] && BOOT_CONFIG="/boot/config.txt"

# Detect HifiBerry MiniAmp via I2S device tree
HIFIBERRY_DETECTED=false
if grep -q "hifiberry" /proc/device-tree/soc/sound/compatible 2>/dev/null; then
    HIFIBERRY_DETECTED=true
elif aplay -l 2>/dev/null | grep -qi "hifiberry"; then
    HIFIBERRY_DETECTED=true
elif grep -q "dtoverlay=hifiberry-dac" "$BOOT_CONFIG" 2>/dev/null; then
    HIFIBERRY_DETECTED=true
fi

if [ "$HIFIBERRY_DETECTED" = true ]; then
    echo "  HifiBerry erkannt — I2S-Audio wird konfiguriert."
    if ! grep -q "dtoverlay=hifiberry-dac" "$BOOT_CONFIG"; then
        sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$BOOT_CONFIG"
        echo "" >> "$BOOT_CONFIG"
        echo "# Tonado: HifiBerry MiniAmp" >> "$BOOT_CONFIG"
        echo "dtoverlay=hifiberry-dac" >> "$BOOT_CONFIG"
        echo "gpio=25=op,dh" >> "$BOOT_CONFIG"
        NEEDS_REBOOT=true
    fi
else
    echo "  Kein HifiBerry erkannt — Onboard-Audio wird verwendet."
    echo "  (HifiBerry kann später über die Einstellungen aktiviert werden.)"
    # Ensure onboard audio is enabled
    if grep -q "^#dtparam=audio=on" "$BOOT_CONFIG"; then
        sed -i 's/^#dtparam=audio=on/dtparam=audio=on/' "$BOOT_CONFIG"
        NEEDS_REBOOT=true
    fi
fi

echo "[5/11] MPD konfigurieren..."
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

audio_output {
    type            "httpd"
    name            "Browser"
    encoder         "lame"
    port            "8090"
    bitrate         "128"
    format          "44100:16:2"
    always_on       "no"
    tags            "yes"
}
MPD

chown -R mpd:audio /var/lib/mpd
# Allow MPD to read media files
usermod -aG "$TONADO_USER" mpd 2>/dev/null || true
chmod 750 "$MEDIA_DIR"
systemctl enable mpd
systemctl restart mpd || true

echo "[6/11] Hardware-Interfaces prüfen..."

# Check for USB RFID reader (works without SPI/I2C)
USB_RFID=false
for hidraw in /dev/hidraw*; do
    [ -e "$hidraw" ] && USB_RFID=true && break
done

if [ "$USB_RFID" = true ]; then
    echo "  USB RFID-Reader erkannt — SPI/I2C für RFID nicht nötig."
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
    echo "  SPI: aktiviert (hinzugefügt)."
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
    echo "  I2C: aktiviert (hinzugefügt)."
    NEEDS_REBOOT=true
fi

# Verify kernel modules can be loaded (if no reboot needed)
if [ "$NEEDS_REBOOT" = false ]; then
    modprobe spidev 2>/dev/null && echo "  SPI-Modul: geladen." || true
    modprobe i2c-dev 2>/dev/null && echo "  I2C-Modul: geladen." || true
fi

echo "[7/11] systemd-Service installieren..."
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

echo "[8/11] Frontend prüfen..."
# Frontend is pre-built and committed to the repository.
# Node.js is NOT installed on the Pi to save disk space (~500 MB).
if [ -d "$TONADO_DIR/web/build" ] && [ -f "$TONADO_DIR/web/build/index.html" ]; then
    echo "  Frontend-Build gefunden."
else
    echo "  HINWEIS: Kein Frontend-Build gefunden!"
    echo "  Möglicherweise ist das Repository nicht vollständig geklont."
    echo "  Versuche: cd $TONADO_DIR && git checkout main -- web/build/"
fi

# Prepare dnsmasq lease file for captive portal
touch /var/lib/misc/dnsmasq.leases 2>/dev/null || true
chown dnsmasq:nogroup /var/lib/misc/dnsmasq.leases 2>/dev/null || true

echo "[9/11] Nginx Reverse Proxy konfigurieren..."
cat > /etc/nginx/sites-available/tonado <<'NGINX'
server {
    listen 80 default_server;
    server_name _;

    # Static frontend (built files)
    root /opt/tonado/web/build;
    index index.html;

    # Upload limit (default 1 MB is too small for audio files)
    client_max_body_size 500M;

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

echo "[10/11] System optimieren..."

# Disable unnecessary services to save RAM and CPU
systemctl disable --now bluetooth 2>/dev/null || true
systemctl disable --now triggerhappy 2>/dev/null || true
systemctl disable --now ModemManager 2>/dev/null || true

# Limit journal size (saves SD card writes)
if [ -d /etc/systemd/journald.conf.d ]; then
    true
else
    mkdir -p /etc/systemd/journald.conf.d
fi
cat > /etc/systemd/journald.conf.d/tonado.conf <<JOURNAL
[Journal]
SystemMaxUse=30M
MaxRetentionSec=7day
JOURNAL
systemctl restart systemd-journald 2>/dev/null || true

# Disable IPv6 (saves RAM on Pi Zero W)
if ! grep -q "ipv6.disable=1" /boot/firmware/cmdline.txt 2>/dev/null; then
    sed -i 's/$/ ipv6.disable=1/' /boot/firmware/cmdline.txt 2>/dev/null || true
    NEEDS_REBOOT=true
fi

echo "  Bluetooth, Triggerhappy, ModemManager deaktiviert."
echo "  Journal-Limit: 30 MB / 7 Tage."
echo "  IPv6 deaktiviert."

echo "[11/11] Hardware-Erkennung..."

# Keep user-chosen hostname from Raspberry Pi Imager
CURRENT_HOSTNAME=$(cat /etc/hostname 2>/dev/null || echo "raspberrypi")
echo "  Hostname: ${CURRENT_HOSTNAME} (erreichbar als ${CURRENT_HOSTNAME}.local)"

# Run hardware detection
if [ -f "$TONADO_DIR/core/hardware/detect.py" ]; then
    echo "  Hardware-Erkennung wird ausgeführt..."
    sudo -u "$TONADO_USER" "$TONADO_DIR/.venv/bin/python" -c \
        "from core.hardware.detect import detect_all; r = detect_all(); print(f'  Erkannt: {r}')" \
        2>/dev/null || echo "  Hardware-Erkennung übersprungen (wird beim ersten Start nachgeholt)."
fi

# Final permissions fix — must run LAST, after all files are in place
chown -R "$TONADO_USER:$TONADO_USER" "$TONADO_DIR"
chmod -R 755 "$TONADO_DIR/web/build" 2>/dev/null || true

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Tonado läuft auf:"
echo "  http://${IP} (Nginx, Port 80)"
echo "  http://${CURRENT_HOSTNAME}.local"
echo ""

if [ "$NEEDS_REBOOT" = true ]; then
    echo "WICHTIG: Hardware-Konfiguration geändert (SPI/I2C/Audio/Hostname)."
    echo "Neustart erforderlich:"
    echo "  sudo reboot"
fi
echo ""
