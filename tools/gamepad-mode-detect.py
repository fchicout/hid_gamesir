#!/usr/bin/env python3
"""
GameSir & Multi-Platform Controller Mode Detector
Identifies the active hardware mode:
  - PlayStation 4 (DS4) Mode (VID: 0x054c, PID: 0x09cc)
  - Xbox 360 / Xbox One (X-Input) Mode (VID: 0x045e, PID: 0x028e/0x02d1/0x0b12)
  - Nintendo Switch Pro Mode (VID: 0x057e, PID: 0x2009)
  - DirectInput / Android Mode (Generic HID)
Supports --watch mode for live monitoring during plug/unplug or mode hotkey changes.
"""

import sys
import time
import glob
import argparse
from pathlib import Path
from datetime import datetime

BOLD = "\033[1m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[1;36m"
MAGENTA = "\033[1;35m"
BLUE = "\033[1;34m"
GRAY = "\033[0;90m"
RESET = "\033[0m"
CLEAR_SCREEN = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

KNOWN_MODES = {
    ("054c", "09cc"): {
        "mode": "PlayStation 4 (DS4 Mode)",
        "protocol": "DualShock 4 HID",
        "expected_driver": "hid-gamesir / hid-playstation",
        "features": "Touchpad, Gyroscope/IMU, Lightbar, Stereo Audio",
        "hotkey_hint": "Hold 'Home + X' or 'Home + B' at plug-in to switch to Xbox mode",
    },
    ("054c", "05c4"): {
        "mode": "PlayStation 4 (DS4 v1 Mode)",
        "protocol": "DualShock 4 HID",
        "expected_driver": "hid-gamesir / hid-playstation",
        "features": "Touchpad, Gyroscope/IMU, Lightbar",
        "hotkey_hint": "Hold 'Home + X' or 'Home + B' at plug-in to switch to Xbox mode",
    },
    ("054c", "0ce6"): {
        "mode": "PlayStation 5 (DualSense Mode)",
        "protocol": "DualSense HID",
        "expected_driver": "hid-playstation",
        "features": "Touchpad, Adaptive Triggers, Haptic Rumble, Gyro",
        "hotkey_hint": "",
    },
    ("045e", "028e"): {
        "mode": "Xbox 360 (X-Input Mode)",
        "protocol": "X-Input (Direct USB / GIP)",
        "expected_driver": "xpad",
        "features": "Standard 14 buttons, Dual Analog Triggers, Dual Rumble Motors",
        "hotkey_hint": "Hold 'Home + A' or 'Home + B' to switch modes",
    },
    ("045e", "02d1"): {
        "mode": "Xbox One (X-Input Mode)",
        "protocol": "X-Input / GIP",
        "expected_driver": "xpad / xone",
        "features": "Impulse Triggers, Standard Xbox Layout",
        "hotkey_hint": "Hold 'Home + A' or 'Home + B' to switch modes",
    },
    ("045e", "0b12"): {
        "mode": "Xbox Series X|S (X-Input Mode)",
        "protocol": "X-Input / BLE GIP",
        "expected_driver": "xpad / xone",
        "features": "Share Button, Hybrid D-pad, Standard Xbox Layout",
        "hotkey_hint": "",
    },
    ("057e", "2009"): {
        "mode": "Nintendo Switch Pro Mode",
        "protocol": "Switch Pro Subcommand Protocol",
        "expected_driver": "hid-nintendo",
        "features": "Nintendo A/B X/Y layout, Motion Sensor, HD Rumble",
        "hotkey_hint": "Hold 'Home + X' while plugging in for PC/Xbox mode",
    },
}


def scan_controllers() -> str:
    lines = []
    lines.append(
        f"{CYAN}========================================================================{RESET}"
    )
    lines.append(
        f"{BOLD} 🎮 Multi-Platform Gamepad Mode Detector{RESET}  {GRAY}[{datetime.now().strftime('%H:%M:%S')}]{RESET}"
    )
    lines.append(
        f"{CYAN}========================================================================{RESET}\n"
    )

    found_any = False

    for dev_path in sorted(glob.glob("/sys/bus/usb/devices/*")):
        p = Path(dev_path)
        id_vendor_f = p / "idVendor"
        id_product_f = p / "idProduct"

        if not id_vendor_f.exists() or not id_product_f.exists():
            continue

        try:
            vid = id_vendor_f.read_text().strip().lower()
            pid = id_product_f.read_text().strip().lower()
            manufacturer = (
                (p / "manufacturer").read_text().strip()
                if (p / "manufacturer").exists()
                else "Unknown"
            )
            product = (p / "product").read_text().strip() if (p / "product").exists() else "Unknown"
            devnum = (p / "devnum").read_text().strip() if (p / "devnum").exists() else "?"
            busnum = (p / "busnum").read_text().strip() if (p / "busnum").exists() else "?"
        except Exception:
            continue

        key = (vid, pid)
        is_gamesir = (
            "chicken run" in manufacturer.lower()
            or "gamesir" in manufacturer.lower()
            or "gamesir" in product.lower()
        )

        if key in KNOWN_MODES or is_gamesir:
            found_any = True
            mode_info = KNOWN_MODES.get(
                key,
                {
                    "mode": "Custom / DirectInput Mode",
                    "protocol": "Generic HID",
                    "expected_driver": "hid-generic",
                    "features": "Standard Gamepad Buttons & Axes",
                    "hotkey_hint": "Refer to GameSir user manual for mode shortcuts",
                },
            )

            # Find active driver
            active_driver = "None"
            for child in p.glob("*:*"):
                driver_link = child / "driver"
                if driver_link.exists():
                    active_driver = driver_link.resolve().name
                    break

            for hid_child in p.glob("*:*/*:*"):
                driver_link = hid_child / "driver"
                if driver_link.exists():
                    active_driver = driver_link.resolve().name

            tag = f"{GREEN}[GAMESIR CONTROLLER]{RESET}" if is_gamesir else f"{BLUE}[GAMEPAD]{RESET}"

            lines.append(f"{tag} {BOLD}{product}{RESET} {GRAY}(Bus {busnum}, Dev {devnum}){RESET}")
            lines.append(f"  {BOLD}Active Mode:{RESET}      {YELLOW}{mode_info['mode']}{RESET}")
            lines.append(
                f"  {BOLD}Hardware VID:PID:{RESET} 0x{vid}:0x{pid} (Manufacturer: {manufacturer})"
            )
            lines.append(f"  {BOLD}Protocol:{RESET}         {mode_info['protocol']}")
            lines.append(
                f"  {BOLD}Bound Driver:{RESET}     {CYAN}{active_driver}{RESET} (Expected: {mode_info['expected_driver']})"
            )
            lines.append(f"  {BOLD}Capabilities:{RESET}     {mode_info['features']}")

            if mode_info.get("hotkey_hint"):
                lines.append(
                    f"  {BOLD}Mode Switch Tip:{RESET}  {GRAY}{mode_info['hotkey_hint']}{RESET}"
                )
            lines.append("-" * 72)

    if not found_any:
        lines.append(
            f"{YELLOW}No recognized gamepad (PS4/Xbox/Switch) found on the USB bus.{RESET}"
        )
        lines.append(
            "Ensure the controller is turned on and connected via USB cable or wireless dongle.\n"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Multi-Platform Gamepad Mode Detector")
    parser.add_argument(
        "-w", "--watch", action="store_true", help="Live watch mode (periodically refreshes screen)"
    )
    parser.add_argument(
        "-n",
        "--interval",
        type=float,
        default=1.0,
        help="Refresh interval in seconds for watch mode (default: 1.0s)",
    )
    args = parser.parse_args()

    if not args.watch:
        print(scan_controllers())
        return

    sys.stdout.write(HIDE_CURSOR)
    try:
        while True:
            output = scan_controllers()
            sys.stdout.write(
                CLEAR_SCREEN
                + output
                + f"\n{GRAY}[Watch mode active (interval: {args.interval}s). Press Ctrl+C to exit]{RESET}\n"
            )
            sys.stdout.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW_CURSOR)
        print("\nExited mode detector.")


if __name__ == "__main__":
    main()
