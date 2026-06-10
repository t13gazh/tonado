#!/bin/bash -e
# Stage 01: system tweaks
# - Copy stage-owned files/ into the rootfs (pi-gen does NOT do this for us)
# - Append Tonado-specific config.txt block (SPI/I2C/OnOff-SHIM overlays)
# - Enable distro-level services (mpd, nginx, avahi)
#
# NOTE: Tonado-owned units (firstrun, imager-wifi-probe, tonado, tonado-ap) are
# NOT enabled here. They live in the repo at /opt/tonado/system/*.service and
# are symlinked + enabled by 04-tonado-finalize, once /opt/tonado exists.
# Single source of truth for unit files = Tonado repo.
#
# Reference: docs/fuer-entwickler/pi-image-architecture.md section 2.6
#
# pi-gen file-placement reality: only 00-packages, *-patches, *-debconf and the
# run.sh/run-chroot.sh hooks are handled by pi-gen's standard logic. Everything
# under files/ must be copied into ${ROOTFS_DIR} EXPLICITLY by this script.
# Scripts run with the substage directory as the working directory, so the
# stage-local files/ tree is reachable relative to "${BASH_SOURCE[0]}".

STAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- config.txt hardware overlays ---
# The boot config path differs by architecture:
#   arm64 (Pi 3B+/4/5): /boot/firmware/config.txt
#   armhf (Pi Zero W):   /boot/config.txt
# Append our block to whichever exists. If NEITHER exists the stage2 boot
# config is missing and the image would boot without SPI/I2C/OnOff-SHIM
# (RFID + gyro dead) — fail loudly instead of silently skipping.
CONFIG_APPEND="${STAGE_DIR}/files/boot/firmware/config.txt.append"
if [ ! -f "${CONFIG_APPEND}" ]; then
    echo "ERROR: ${CONFIG_APPEND} missing from the stage tree." >&2
    exit 1
fi

BOOT_CONFIG=""
for candidate in \
    "${ROOTFS_DIR}/boot/firmware/config.txt" \
    "${ROOTFS_DIR}/boot/config.txt"; do
    if [ -f "${candidate}" ]; then
        BOOT_CONFIG="${candidate}"
        break
    fi
done

if [ -z "${BOOT_CONFIG}" ]; then
    echo "ERROR: No boot config.txt found under ${ROOTFS_DIR}/boot[/firmware]." >&2
    echo "       Cannot enable SPI/I2C/OnOff-SHIM — refusing to build a broken image." >&2
    exit 1
fi

echo "Appending Tonado hardware overlays to ${BOOT_CONFIG}"
{
    echo ""
    echo "# --- Tonado hardware overlays (appended by stage-tonado) ---"
    cat "${CONFIG_APPEND}"
} >> "${BOOT_CONFIG}"

on_chroot << EOF
# Enable core distro services (won't start here, only when the device boots)
systemctl enable mpd.service
systemctl enable nginx.service
systemctl enable avahi-daemon.service
EOF
