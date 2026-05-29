#!/usr/bin/env bash
# Smoke-test a built Tonado pi-gen image.
#
# Two layers, by design:
#   1. Offline rootfs inspection (HARD asserts). Deterministic, no emulation.
#      Catches the regressions that actually happen when the stage breaks:
#      missing committed frontend, missing venv, units not enabled, no install
#      marker. This is the part that must stay green.
#   2. QEMU boot + HTTP /api/health (BEST EFFORT, never fatal). raspi3b
#      networking in QEMU is historically flaky; a boot failure here only logs
#      a warning. Harden this incrementally — the CI job is continue-on-error.
#
# Usage: qemu-smoke.sh <image.img.xz>
# Reference: docs/fuer-entwickler/pi-image-ci.md section 6.

set -euo pipefail

IMG_XZ="${1:?usage: qemu-smoke.sh <image.img.xz>}"
WORK="$(mktemp -d)"
LOOP=""

cleanup() {
  sudo umount "$WORK/root" 2>/dev/null || true
  sudo umount "$WORK/boot" 2>/dev/null || true
  [ -n "$LOOP" ] && sudo losetup -d "$LOOP" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "::group::Decompress image"
cp "$IMG_XZ" "$WORK/"
XZ_BASE="$(basename "$IMG_XZ")"
xz -dk "$WORK/$XZ_BASE"
IMG="$WORK/${XZ_BASE%.xz}"
ls -la "$WORK"
echo "::endgroup::"

echo "::group::Map partitions"
LOOP="$(sudo losetup --show -fP "$IMG")"
echo "loop device: $LOOP"
sudo partprobe "$LOOP" 2>/dev/null || true
ls -la "${LOOP}"* || true
echo "::endgroup::"

echo "::group::Offline rootfs checks"
mkdir -p "$WORK/root"
# pi-gen layout: p1 = boot (FAT), p2 = root (ext4).
sudo mount "${LOOP}p2" "$WORK/root"
R="$WORK/root"
fail=0
check() {
  if eval "$2"; then
    echo "  OK   $1"
  else
    echo "  FAIL $1" >&2
    fail=1
  fi
}

check "frontend committed (web/build/index.html)" \
  "[ -f '$R/opt/tonado/web/build/index.html' ]"
check "python venv present" \
  "[ -x '$R/opt/tonado/.venv/bin/python' ] || [ -x '$R/opt/tonado/.venv/bin/python3' ]"
check "pyproject.toml present" \
  "[ -f '$R/opt/tonado/pyproject.toml' ]"
check "install marker (source=pi-gen)" \
  "grep -q 'source=pi-gen' '$R/var/lib/tonado/install.done' 2>/dev/null"

for unit in tonado tonado-ap firstrun imager-wifi-probe; do
  check "unit linked: $unit.service" \
    "[ -e '$R/etc/systemd/system/$unit.service' ]"
  check "unit enabled: $unit.service" \
    "ls $R/etc/systemd/system/*.wants/$unit.service >/dev/null 2>&1"
done
for unit in mpd nginx avahi-daemon; do
  check "distro unit enabled: $unit" \
    "ls $R/etc/systemd/system/multi-user.target.wants/$unit.service >/dev/null 2>&1"
done

# Build-only packages must be gone (03-tonado-finalize purges them).
check "build-essential purged" \
  "[ ! -e '$R/usr/bin/gcc' ]"
echo "::endgroup::"

if [ "$fail" -ne 0 ]; then
  echo "Offline rootfs checks FAILED." >&2
  exit 1
fi
echo "Offline rootfs checks passed."

# --- Layer 2: QEMU boot (best effort, non-fatal) --------------------------
echo "::group::QEMU boot smoke (best effort)"
qemu_smoke() {
  command -v qemu-system-aarch64 >/dev/null || {
    echo "qemu-system-aarch64 not installed — skipping boot test."; return 0; }

  mkdir -p "$WORK/boot"
  sudo mount "${LOOP}p1" "$WORK/boot"
  local kernel dtb
  kernel="$(ls "$WORK/boot"/kernel8.img 2>/dev/null | head -n1 || true)"
  dtb="$(ls "$WORK/boot"/bcm2710-rpi-3-b-plus.dtb "$WORK/boot"/bcm2837-rpi-3-b*.dtb 2>/dev/null | head -n1 || true)"
  if [ -z "$kernel" ] || [ -z "$dtb" ]; then
    echo "kernel8.img or rpi-3 dtb not found in boot partition — skipping boot." >&2
    ls -la "$WORK/boot" || true
    return 0
  fi
  cp "$kernel" "$WORK/kernel8.img"
  cp "$dtb" "$WORK/rpi3.dtb"
  sudo umount "$WORK/boot"

  # nginx fronts the app on port 80 (uvicorn binds 127.0.0.1:8080 only).
  qemu-system-aarch64 \
    -M raspi3b -cpu cortex-a72 -smp 4 -m 1G \
    -kernel "$WORK/kernel8.img" -dtb "$WORK/rpi3.dtb" \
    -drive "file=$IMG,format=raw,if=sd" \
    -append "console=ttyAMA0,115200 root=/dev/mmcblk0p2 rootwait rw" \
    -nographic \
    -netdev user,id=net0,hostfwd=tcp::5080-:80 \
    -device usb-net,netdev=net0 \
    > "$WORK/qemu.log" 2>&1 &
  local qpid=$!

  local ok=0
  for i in $(seq 1 36); do  # ~6 min budget
    if ! kill -0 "$qpid" 2>/dev/null; then
      echo "QEMU exited early." >&2; break
    fi
    if curl -fsS --max-time 5 "http://localhost:5080/api/health" >/dev/null 2>&1; then
      ok=1; break
    fi
    sleep 10
  done

  kill "$qpid" 2>/dev/null || true
  wait "$qpid" 2>/dev/null || true

  if [ "$ok" -eq 1 ]; then
    echo "QEMU boot smoke PASSED: /api/health reachable."
  else
    echo "WARNING: QEMU boot smoke did not reach /api/health (non-fatal)." >&2
    echo "----- last 60 lines of QEMU log -----" >&2
    tail -n 60 "$WORK/qemu.log" 2>/dev/null || true
  fi
}
qemu_smoke || echo "WARNING: QEMU smoke wrapper errored (non-fatal)." >&2
echo "::endgroup::"
