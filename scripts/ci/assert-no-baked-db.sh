#!/usr/bin/env bash
# Build-guard: refuse to ship an image that baked a SQLite database.
#
# WHY (supply-chain / security): core/settings.py points the app DB at
#   /opt/tonado/config/tonado.db
# That file is .gitignore'd, so the in-chroot `git clone` (stage 02) must NEVER
# bring one into /opt/tonado/config. If a tonado.db DID leak into the image,
# every flashed device would boot with the SAME pre-seeded DB — meaning a
# shared, predictable per-device JWT secret and shared auth state across all
# boxes. The DB (and its JWT secret) must be generated fresh on first boot.
#
# This guard FAILS LOUD (exit 1) the moment it finds any tonado.db under the
# image's /opt/tonado/config. It must stay a BLOCKING step (not the
# continue-on-error qemu-smoke job) and run for PRs too.
#
# Accepts either:
#   - a path to the unpacked rootfs (a directory containing opt/tonado/...), or
#   - a path to the built image (.img or .img.xz), which it loop-mounts.
#
# Usage:
#   assert-no-baked-db.sh <rootfs-dir | image.img | image.img.xz>
# Reference: docs/fuer-entwickler/pi-image-ci.md.

set -euo pipefail

TARGET="${1:?usage: assert-no-baked-db.sh <rootfs-dir | image.img(.xz)>}"

# Path inside the rootfs where the app expects its DB (core/settings.py).
DB_REL="opt/tonado/config/tonado.db"

WORK=""
LOOP=""
MOUNTED=""
cleanup() {
  [ -n "$MOUNTED" ] && sudo umount "$MOUNTED" 2>/dev/null || true
  [ -n "$LOOP" ] && sudo losetup -d "$LOOP" 2>/dev/null || true
  [ -n "$WORK" ] && rm -rf "$WORK" || true
}
trap cleanup EXIT

# Resolve TARGET to a rootfs directory R.
R=""
if [ -d "$TARGET" ]; then
  R="$TARGET"
else
  WORK="$(mktemp -d)"
  IMG="$TARGET"
  case "$TARGET" in
    *.xz)
      cp "$TARGET" "$WORK/"
      base="$(basename "$TARGET")"
      xz -dk "$WORK/$base"
      IMG="$WORK/${base%.xz}"
      ;;
  esac
  LOOP="$(sudo losetup --show -fP "$IMG")"
  sudo partprobe "$LOOP" 2>/dev/null || true
  mkdir -p "$WORK/root"
  # pi-gen layout: p1 = boot (FAT), p2 = root (ext4).
  sudo mount "${LOOP}p2" "$WORK/root"
  MOUNTED="$WORK/root"
  R="$WORK/root"
fi

DB_PATH="$R/$DB_REL"
if [ -e "$DB_PATH" ]; then
  echo "FAIL: baked SQLite DB found in image: /$DB_REL" >&2
  echo "  A tonado.db must NOT be present in the cloned repo — it would give" >&2
  echo "  every device the SAME per-device JWT secret and shared auth state." >&2
  echo "  Ensure config/tonado.db stays .gitignore'd and is not committed." >&2
  ls -la "$DB_PATH" >&2 || true
  exit 1
fi

# Defense in depth: catch a DB landing anywhere under opt/tonado/config.
CFG_DIR="$R/opt/tonado/config"
if [ -d "$CFG_DIR" ]; then
  STRAY="$(find "$CFG_DIR" -maxdepth 2 -type f -name '*.db' 2>/dev/null || true)"
  if [ -n "$STRAY" ]; then
    echo "FAIL: stray *.db file(s) baked under /opt/tonado/config:" >&2
    echo "$STRAY" >&2
    exit 1
  fi
fi

echo "OK: no baked tonado.db in image (config DB will be seeded on first boot)."
