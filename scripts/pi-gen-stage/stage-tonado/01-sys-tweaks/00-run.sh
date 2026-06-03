#!/bin/bash -e
# Stage 01: system tweaks
# - Enable distro-level services (mpd, nginx, avahi)
# - Append Tonado-specific config.txt block
#
# NOTE: Tonado-owned units (firstrun, imager-wifi-probe, tonado, tonado-ap) are
# NOT enabled here. They live in the repo at /opt/tonado/system/*.service and
# are symlinked + enabled by 03-tonado-finalize, once /opt/tonado exists.
# Single source of truth for unit files = Tonado repo.
#
# Reference: docs/fuer-entwickler/pi-image-architecture.md section 2.6
# Files from files/ are copied by pi-gen's standard file-placement logic.

# Append the Tonado-specific config.txt block to the stage2-provided config.
if [ -f "${ROOTFS_DIR}/boot/firmware/config.txt.append" ]; then
    cat "${ROOTFS_DIR}/boot/firmware/config.txt.append" \
        >> "${ROOTFS_DIR}/boot/firmware/config.txt"
    rm "${ROOTFS_DIR}/boot/firmware/config.txt.append"
fi

on_chroot << EOF
# Enable core distro services (won't start here, only when the device boots)
systemctl enable mpd.service
systemctl enable nginx.service
systemctl enable avahi-daemon.service
EOF
