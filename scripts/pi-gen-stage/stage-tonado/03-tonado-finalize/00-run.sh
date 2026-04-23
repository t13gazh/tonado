#!/bin/bash -e
# Stage 03: post-install cleanup and wiring
# - Purge build-only apt packages to shrink image
# - Chown repo to pi:pi
# - Symlink repo-shipped systemd units into /etc/systemd/system and enable them
# - Create install marker so system/install.sh short-circuits if a tinkerer runs
#   it later on an image-installed device
#
# Reference: docs/fuer-entwickler/pi-image-architecture.md section 2.6

set -euo pipefail

: "${TONADO_VERSION:=unknown}"

on_chroot << EOF
set -euo pipefail

# --- Shrink: drop build-only packages ---
apt-get purge -y python3-dev build-essential libffi-dev
apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*.deb

# --- Ownership ---
chown -R pi:pi /opt/tonado
# web/build is served by nginx and must be world-readable.
chmod -R a+rX /opt/tonado/web/build

# --- Systemd units shipped inside the repo (single source of truth) ---
# All Tonado-owned units live at /opt/tonado/system/*.service. Symlink them
# into /etc/systemd/system so 'systemctl enable' can pick them up.
# Order matters: firstrun runs first, imager-wifi-probe decides AP vs. STA,
# tonado-ap + tonado are the primary services.
for unit in firstrun.service imager-wifi-probe.service tonado.service tonado-ap.service; do
    if [ ! -f "/opt/tonado/system/\${unit}" ]; then
        echo "ERROR: Expected unit /opt/tonado/system/\${unit} missing from repo." >&2
        exit 1
    fi
    ln -sf "/opt/tonado/system/\${unit}" "/etc/systemd/system/\${unit}"
done

# Enable Tonado units. firstrun + imager-wifi-probe are gated by
# ConditionPathExists / Wants so enabling them at image-bake time is safe.
systemctl enable firstrun.service
systemctl enable imager-wifi-probe.service
systemctl enable tonado.service
systemctl enable tonado-ap.service

# --- Hardware group membership for the pi user ---
usermod -aG audio,spi,i2c,gpio pi
# MPD needs access to pi-owned media dir.
usermod -aG pi mpd || true

# --- Runtime directories ---
install -d -o pi -g pi -m 755 /opt/tonado/config
install -d -o pi -g pi -m 755 /home/pi/tonado/media
install -d -o pi -g pi -m 755 /home/pi/tonado/media/.playlists

# --- Install marker ---
# system/install.sh checks /var/lib/tonado/install.done and short-circuits. For
# image-installed devices we want the same guarantee, plus a source tag so we
# can distinguish them in support.
install -d -o root -g root -m 755 /var/lib/tonado
cat > /var/lib/tonado/install.done <<MARKER
Tonado image-installed \$(date -Iseconds)
source=pi-gen
tonado_version=${TONADO_VERSION}
MARKER
chmod 644 /var/lib/tonado/install.done
EOF
