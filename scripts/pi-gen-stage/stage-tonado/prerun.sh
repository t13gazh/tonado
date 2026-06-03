#!/bin/bash -e
# pi-gen stage hook: copy previous stage rootfs into this stage workspace.
# Standard pattern -- same body as stage2/prerun.sh in RPi-Distro/pi-gen.

if [ ! -d "${ROOTFS_DIR}" ]; then
    copy_previous
fi
