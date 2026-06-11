#!/bin/bash
# Tonado audio overlay activation helper.
#
# The setup wizard writes the `audio.device` config key but cannot, by itself,
# activate the I2S DAC: that requires editing the firmware config.txt and a
# reboot. Without the overlay the DAC stays silent and the wizard's test tone
# produces no sound. This privileged helper performs that one config.txt edit.
#
# Usage:
#   apply-audio-overlay.sh i2s      # enable HifiBerry DAC overlay (mute onboard)
#   apply-audio-overlay.sh analog   # re-enable onboard 3.5mm audio (drop overlay)
#
# FIXED argv only — the sudoers grant whitelists exactly these two invocations
# (no wildcard). Both directions are idempotent.
#
# The edit logic (sed/grep) is kept BYTE-IDENTICAL to the HifiBerry block in
# system/install.sh so the two paths can never drift into duplicate lines.
#
# This helper only writes config.txt. A reboot is required for the overlay to
# take effect; the backend owns the reboot UX.

set -euo pipefail

# Default overlay matches install.sh (override only for Amp2 / DAC+ boards via
# HIFIBERRY_OVERLAY; the wizard does not currently pass one).
HIFIBERRY_OVERLAY="${HIFIBERRY_OVERLAY:-hifiberry-dac}"

usage() {
    echo "usage: apply-audio-overlay.sh {i2s|analog}" >&2
    exit 2
}

[ "$#" -eq 1 ] || usage
MODE="$1"

# Resolve config.txt: Bookworm uses /boot/firmware, older images /boot.
BOOT_CONFIG="/boot/firmware/config.txt"
[ ! -f "$BOOT_CONFIG" ] && BOOT_CONFIG="/boot/config.txt"
if [ ! -f "$BOOT_CONFIG" ]; then
    echo "ERROR: config.txt not found (checked /boot/firmware/config.txt and /boot/config.txt)." >&2
    exit 1
fi

case "$MODE" in
    i2s)
        # Enable I2S DAC. IDENTICAL to install.sh's HifiBerry-detected branch:
        # guard on any hifiberry-* overlay so a re-run never appends a duplicate.
        if ! grep -qE "^dtoverlay=hifiberry-" "$BOOT_CONFIG"; then
            sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$BOOT_CONFIG"
            echo "" >> "$BOOT_CONFIG"
            echo "# Tonado: HifiBerry (${HIFIBERRY_OVERLAY})" >> "$BOOT_CONFIG"
            echo "dtoverlay=${HIFIBERRY_OVERLAY}" >> "$BOOT_CONFIG"
            echo "gpio=25=op,dh" >> "$BOOT_CONFIG"
            echo "I2S-Audio aktiviert (${HIFIBERRY_OVERLAY}). Ein Neustart ist erforderlich."
        else
            echo "I2S-Audio bereits aktiviert — keine Änderung."
        fi
        ;;
    analog)
        # Re-enable onboard analog audio and drop the HifiBerry overlay. Reverse
        # of the i2s branch; idempotent (no-op when already analog).
        CHANGED=false
        # Re-enable onboard audio (mirrors install.sh's no-HifiBerry branch).
        if grep -q "^#dtparam=audio=on" "$BOOT_CONFIG"; then
            sed -i 's/^#dtparam=audio=on/dtparam=audio=on/' "$BOOT_CONFIG"
            CHANGED=true
        fi
        # Comment out the HifiBerry overlay + its companion lines if present.
        if grep -qE "^dtoverlay=hifiberry-" "$BOOT_CONFIG"; then
            sed -i 's/^dtoverlay=hifiberry-/#dtoverlay=hifiberry-/' "$BOOT_CONFIG"
            sed -i 's/^gpio=25=op,dh/#gpio=25=op,dh/' "$BOOT_CONFIG"
            CHANGED=true
        fi
        if [ "$CHANGED" = true ]; then
            echo "Onboard-Audio aktiviert. Ein Neustart ist erforderlich."
        else
            echo "Onboard-Audio bereits aktiv — keine Änderung."
        fi
        ;;
    *)
        usage
        ;;
esac

exit 0
