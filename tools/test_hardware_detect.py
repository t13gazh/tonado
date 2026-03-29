#!/usr/bin/env python3
"""Quick hardware detection test — run on Pi to verify auto-detection."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")

from core.hardware.detect import (
    detect_pi_model,
    detect_rfid,
    detect_audio,
    detect_gyro,
    detect_gpio,
    detect_all,
)


def main() -> None:
    print("=" * 60)
    print("TONADO HARDWARE DETECTION TEST")
    print("=" * 60)

    # Step-by-step detection with detailed output
    print("\n--- Pi Model ---")
    pi = detect_pi_model()
    print(f"  Model:     {pi.model}")
    print(f"  Revision:  {pi.revision}")
    print(f"  RAM:       {pi.ram_mb} MB")
    print(f"  WiFi:      {pi.has_wifi}")
    print(f"  Bluetooth: {pi.has_bluetooth}")
    print(f"  Supported: {pi.supported}")

    print("\n--- RFID Reader ---")
    rfid_type, rfid_device = detect_rfid()
    print(f"  Type:   {rfid_type}")
    print(f"  Device: {rfid_device or '(none)'}")

    # Extra diagnostics for RFID
    print("\n  Diagnostics:")
    spi = Path("/dev/spidev0.0")
    print(f"    /dev/spidev0.0 exists: {spi.exists()}")
    i2c = Path("/dev/i2c-1")
    print(f"    /dev/i2c-1 exists:     {i2c.exists()}")
    for i in range(4):
        p = Path(f"/dev/hidraw{i}")
        if p.exists():
            print(f"    /dev/hidraw{i} exists:   True")

    # Check SPI module loaded
    try:
        modules = Path("/proc/modules").read_text()
        spi_loaded = "spi_bcm2835" in modules or "spidev" in modules
        print(f"    SPI kernel module:     {'loaded' if spi_loaded else 'NOT loaded'}")
    except Exception:
        pass

    # Check i2cdetect output if available
    try:
        import subprocess
        result = subprocess.run(
            ["i2cdetect", "-y", "1"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            print(f"\n  I2C bus scan (i2cdetect -y 1):")
            for line in result.stdout.splitlines():
                print(f"    {line}")
    except FileNotFoundError:
        print("    i2cdetect not available (install: sudo apt install i2c-tools)")
    except Exception as e:
        print(f"    i2cdetect error: {e}")

    print("\n--- Audio ---")
    audio = detect_audio()
    if audio:
        for a in audio:
            rec = " [RECOMMENDED]" if a.recommended else ""
            print(f"  {a.name} ({a.type}) — {a.device}{rec}")
    else:
        print("  No audio outputs detected")

    # Show raw ALSA cards
    cards = Path("/proc/asound/cards")
    if cards.exists():
        print(f"\n  Raw /proc/asound/cards:")
        for line in cards.read_text().splitlines():
            if line.strip():
                print(f"    {line}")

    print("\n--- Gyro (MPU6050) ---")
    gyro = detect_gyro()
    print(f"  Detected: {gyro}")

    print("\n--- GPIO ---")
    gpio = detect_gpio()
    print(f"  Available: {gpio}")

    print("\n--- Full Profile (JSON) ---")
    profile = detect_all()
    print(json.dumps(profile.to_dict(), indent=2))

    print("\n" + "=" * 60)
    if profile.rfid_reader != "none":
        print(f"RFID Reader erkannt: {profile.rfid_reader} auf {profile.rfid_device}")
    else:
        print("KEIN RFID Reader erkannt!")
        print("Prüfe: SPI/I2C aktiviert? Reader korrekt angeschlossen?")
    print("=" * 60)


if __name__ == "__main__":
    main()
