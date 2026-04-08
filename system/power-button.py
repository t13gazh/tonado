#!/usr/bin/env python3
"""OnOff SHIM power button listener.

Watches GPIO 3 for a sustained LOW signal (button press) and triggers
a clean shutdown. Runs as a standalone systemd service so it works
independently of the Tonado application.

GPIO 3 is shared with I2C SCL — the kernel's gpio-shutdown overlay
cannot claim it when I2C is active. This script uses gpiod userspace
access which coexists with the I2C driver.

The 1-second hold requirement filters out I2C bus noise (microsecond
glitches) from being misinterpreted as button presses.
"""

import subprocess
import sys
import time

BUTTON_GPIO = 3
HOLD_TIME = 1.0  # seconds — must hold button to trigger shutdown
POLL_INTERVAL = 0.2  # seconds between checks

def main() -> None:
    try:
        import gpiod
    except ImportError:
        print("gpiod not available — power button disabled", file=sys.stderr)
        # Sleep forever so systemd doesn't restart-loop
        while True:
            time.sleep(3600)

    chip = gpiod.Chip("/dev/gpiochip0")

    # gpiod v2 API: request line as input with pull-up
    config = {BUTTON_GPIO: gpiod.LineSettings(
        direction=gpiod.line.Direction.INPUT,
        bias=gpiod.line.Bias.PULL_UP,
    )}
    try:
        request = chip.request_lines(consumer="tonado-power", config=config)
    except OSError as e:
        print(f"Cannot request GPIO {BUTTON_GPIO}: {e}", file=sys.stderr)
        while True:
            time.sleep(3600)

    print(f"Power button listening on GPIO {BUTTON_GPIO}")

    pressed_since = None
    while True:
        value = request.get_value(BUTTON_GPIO)
        if value == gpiod.line.Value.ACTIVE:  # LOW = button pressed
            if pressed_since is None:
                pressed_since = time.monotonic()
            elif time.monotonic() - pressed_since >= HOLD_TIME:
                print("Power button held — shutting down")
                request.release()
                subprocess.run(["shutdown", "-h", "now"])
                sys.exit(0)
        else:
            pressed_since = None
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
