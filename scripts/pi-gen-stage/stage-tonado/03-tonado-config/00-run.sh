#!/bin/bash -e
# Stage 03: network-free configuration steps ported from system/install.sh.
#
# This substage runs AFTER 02-tonado-code (so /opt/tonado exists, including
# system/sudoers.d/tonado) and BEFORE 04-tonado-finalize (chown + unit wiring).
#
# It writes the config files install.sh produces at install time, so a freshly
# flashed image boots headless straight to the setup AP with working nginx,
# MPD, sudoers, SPI/I2C and SD-card-friendly journald limits — without anyone
# ever running install.sh.
#
# install.sh -> stage coverage (the 11 install.sh steps):
#   [1] packages            -> 00-packages
#   [2] directories         -> 04-tonado-finalize (install -d ...)
#   [3] clone + venv        -> 02-tonado-code
#   [4] audio overlay       -> 01-sys-tweaks (config.txt.append; HifiBerry is
#                              opt-in at runtime, not baked — see notes)
#   [5] mpd.conf            -> THIS substage
#   [6] SPI/I2C/OnOff-SHIM  -> 01-sys-tweaks (config.txt.append) + i2c-dev here
#   [7] systemd + sudoers   -> units: 04-tonado-finalize; sudoers: THIS substage
#   [8] frontend + dnsmasq  -> build check: 02-tonado-code; lease file: here
#   [9] nginx site          -> THIS substage (+ captive-portal probe responses)
#  [10] system optimisation -> THIS substage (journald, disable svc, ipv6)
#  [11] hardware detect      -> NOT ported (runtime-only, needs real hardware)
#
# chroot rules: NEVER `systemctl --now`, `restart` or `modprobe` here — nothing
# runs in the chroot. Only write config files (they take effect on real boot)
# and `enable`/`disable` units. `visudo -cf` works in the chroot.

set -euo pipefail

# The media directory MUST match install.sh and 04-tonado-finalize.
# install.sh: MEDIA_DIR="/home/${TONADO_USER}/tonado/media", user = pi.
MEDIA_DIR="/home/pi/tonado/media"

on_chroot << EOF
set -euo pipefail

# =====================================================================
# [5/11] MPD configuration
# =====================================================================
# Verbatim values from install.sh: software mixer for the default ALSA
# output, plus an always-on httpd encoder on :8090 for browser audio.
cat > /etc/mpd.conf <<'MPD'
music_directory     "${MEDIA_DIR}"
playlist_directory  "${MEDIA_DIR}/.playlists"
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
    # always_on keeps the encoder running across track/codec transitions,
    # so the browser-side proxy connection stays valid when tracks change
    # or when the codec (e.g. OGG podcast -> MP3 file) switches.
    always_on       "yes"
    tags            "yes"
}
MPD

# MPD's data dir must be owned by mpd:audio (it ships as root in the rootfs).
chown -R mpd:audio /var/lib/mpd

# =====================================================================
# [6/11] i2c-dev kernel module
# =====================================================================
# config.txt enables the I2C bus (dtparam=i2c_arm=on) but Bookworm does NOT
# auto-load i2c-dev, so /dev/i2c-1 never appears -> MPU6050 gyro + PN532 RFID
# are dead. Project core pitfall. modprobe would no-op in the chroot, so we
# wire it via modules-load.d which takes effect on the real boot.
echo i2c-dev > /etc/modules-load.d/tonado-i2c.conf

# =====================================================================
# [misc] WiFi regulatory domain (bake-time, persistent)
# =====================================================================
# Without a regulatory country the radio stays rfkill-soft-blocked (country
# 00) and hostapd refuses to start -> no setup AP at all. This MUST be baked:
# 'iw reg set' at runtime is not reboot-persistent. raspi-config persists it
# (wpa_supplicant country= + regdb); firstrun.sh additionally runs an rfkill
# unblock at runtime as a belt-and-braces guard. We hardcode DE for now
# (Backlog: country selection in the wizard / i18n).
if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_wifi_country DE || true
fi
# Independent fallback in case raspi-config is absent: make sure the country
# lands in wpa_supplicant.conf, which the kernel regdb honours on boot.
if [ -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
    if ! grep -q '^country=' /etc/wpa_supplicant/wpa_supplicant.conf; then
        sed -i '1i country=DE' /etc/wpa_supplicant/wpa_supplicant.conf
    fi
else
    printf 'country=DE\n' > /etc/wpa_supplicant/wpa_supplicant.conf
    chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf
fi

# =====================================================================
# [7/11] sudoers drop-in
# =====================================================================
# Source lives in the cloned repo. Replace the %TONADO_USER% placeholder with
# the image user (pi), validate with visudo on a temp copy first — a malformed
# grant would brick sudo entirely — then install 0440 root:root.
SUDOERS_SRC="/opt/tonado/system/sudoers.d/tonado"
SUDOERS_TMP="\$(mktemp)"
sed 's/%TONADO_USER%/pi/g' "\${SUDOERS_SRC}" > "\${SUDOERS_TMP}"
if visudo -cf "\${SUDOERS_TMP}" >/dev/null; then
    install -o root -g root -m 0440 "\${SUDOERS_TMP}" /etc/sudoers.d/tonado
    echo "  -> sudoers drop-in installed (/etc/sudoers.d/tonado)"
else
    rm -f "\${SUDOERS_TMP}"
    echo "ERROR: sudoers file invalid, aborting build." >&2
    exit 1
fi
rm -f "\${SUDOERS_TMP}"

# The Raspberry Pi Imager / pi-gen may provision a blanket NOPASSWD:ALL rule.
# With our minimal drop-in in place, that pauschal rule would bypass the
# hardening — drop it AFTER our drop-in installed successfully.
if [ -f /etc/sudoers.d/010_pi-nopasswd ]; then
    echo "  Removing /etc/sudoers.d/010_pi-nopasswd (blanket grant, replaced by minimal drop-in)."
    rm -f /etc/sudoers.d/010_pi-nopasswd
fi

# =====================================================================
# [8/11] dnsmasq lease file for the captive portal
# =====================================================================
touch /var/lib/misc/dnsmasq.leases 2>/dev/null || true
chown dnsmasq:nogroup /var/lib/misc/dnsmasq.leases 2>/dev/null || true

# =====================================================================
# [9/11] nginx reverse proxy + captive-portal auto-open responses
# =====================================================================
# Body matches install.sh (500M upload, /api + /ws proxy to 127.0.0.1:8080,
# SPA try_files, CSP/security headers). PLUS the OS connectivity-probe answers
# so the captive portal opens automatically on the setup AP:
#   - dnsmasq (setup-ap.sh) resolves every hostname to 192.168.4.1, so all OS
#     probes land on this default_server.
#   - Android  /generate_204, /gen_204  -> 302 to the portal (instead of 204)
#   - Windows  /connecttest.txt, /ncsi.txt -> 302 to the portal (instead of the
#     "Microsoft Connect Test" / "Microsoft NCSI" success body)
#   - Apple    /hotspot-detect.html, /library/test/success.html -> 200 with a
#     non-"Success" body (Apple CNA opens when the word "Success" is absent;
#     a 302 here would NOT trigger the CNA reliably).
cat > /etc/nginx/sites-available/tonado <<'NGINX'
server {
    listen 80 default_server;
    server_name _;

    # Static frontend (built files)
    root /opt/tonado/web/build;
    index index.html;

    # Upload limit (default 1 MB is too small for audio files)
    client_max_body_size 500M;

    # Security headers — FastAPI middleware covers /api and /ws, but SPA
    # assets served directly by nginx would otherwise ship without them.
    # "always" keeps them on 4xx/5xx responses too.
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ws: wss:; media-src 'self' blob: http: https:; font-src 'self'" always;

    # --- Captive-portal auto-open: OS connectivity probes ---
    # Android: expects HTTP 204. Returning a 302 makes it show the portal.
    location = /generate_204 { return 302 http://192.168.4.1/; }
    location = /gen_204      { return 302 http://192.168.4.1/; }

    # Windows NCSI: expects "Microsoft Connect Test" / "Microsoft NCSI".
    # A 302 flips the indicator to "no internet, sign in".
    location = /connecttest.txt { return 302 http://192.168.4.1/; }
    location = /ncsi.txt        { return 302 http://192.168.4.1/; }

    # Apple CNA: opens the captive sheet when the body is NOT exactly
    # "<HTML>...Success...</HTML>". Serve a minimal non-Success body.
    location = /hotspot-detect.html {
        default_type text/html;
        return 200 '<HTML><HEAD><TITLE>Tonado</TITLE></HEAD><BODY>Tonado Setup</BODY></HTML>';
    }
    location = /library/test/success.html {
        default_type text/html;
        return 200 '<HTML><HEAD><TITLE>Tonado</TITLE></HEAD><BODY>Tonado Setup</BODY></HTML>';
    }

    # API and WebSocket proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }

    # SPA fallback
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/tonado /etc/nginx/sites-enabled/tonado
rm -f /etc/nginx/sites-enabled/default

# =====================================================================
# [10/11] system optimisation
# =====================================================================
# Journal size limit (saves SD-card writes — children pull the plug).
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/tonado.conf <<'JOURNAL'
[Journal]
SystemMaxUse=30M
MaxRetentionSec=7day
JOURNAL

# Disable services we don't need (saves RAM/CPU on the Pi Zero W).
# NO --now in the chroot: nothing is running here, the disable takes effect on
# the real boot. '|| true' so a unit absent in the base image is non-fatal.
systemctl disable bluetooth.service 2>/dev/null || true
systemctl disable triggerhappy.service 2>/dev/null || true
systemctl disable ModemManager.service 2>/dev/null || true

# CRITICAL: the dnsmasq package ships an enabled dnsmasq.service that binds
# :53 on boot. setup-ap.sh runs its OWN dnsmasq instance (dnsmasq -C ...) for
# the captive portal — if the distro service already holds :53, our instance
# fails with "address already in use" and the setup AP comes up WITHOUT DHCP,
# so the phone never gets an IP. mask (not just disable) so nothing can pull
# it back via socket activation or a dependency. setup-ap.sh invokes the
# binary directly, not the unit, so masking does not affect the portal.
# hostapd.service is masked by default on Debian, but mask it defensively for
# the same reason (we only ever start hostapd via setup-ap.sh -B).
systemctl mask dnsmasq.service 2>/dev/null || true
systemctl mask hostapd.service 2>/dev/null || true

# =====================================================================
# [misc] machine-id + SSH host keys reset (bake-time)
# =====================================================================
# Every flashed image must NOT share the same /etc/machine-id or SSH host
# keys, or all devices look identical on the network and SSH host-key
# warnings collide. Blanking them at bake time makes systemd regenerate
# machine-id and (with firstrun's regen) fresh host keys on first boot.
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
rm -f /etc/ssh/ssh_host_*
EOF

# =====================================================================
# [10/11 cont.] Disable IPv6 via cmdline.txt — OUTSIDE the chroot
# =====================================================================
# cmdline.txt MUST stay single-line or the kernel refuses to boot, and the
# existing init=/resize parameters must be preserved. Append ipv6.disable=1
# to line 1 only. Path differs by arch (arm64 vs armhf), same as config.txt.
CMDLINE=""
for candidate in \
    "${ROOTFS_DIR}/boot/firmware/cmdline.txt" \
    "${ROOTFS_DIR}/boot/cmdline.txt"; do
    if [ -f "${candidate}" ]; then
        CMDLINE="${candidate}"
        break
    fi
done

if [ -z "${CMDLINE}" ]; then
    echo "ERROR: No cmdline.txt found under ${ROOTFS_DIR}/boot[/firmware]." >&2
    exit 1
fi

if ! grep -q "ipv6.disable=1" "${CMDLINE}"; then
    # Touch line 1 only — never append to every line.
    sed -i '1 s/$/ ipv6.disable=1/' "${CMDLINE}"
    echo "  ipv6.disable=1 appended to ${CMDLINE}"
else
    echo "  ipv6.disable=1 already present in ${CMDLINE}"
fi
