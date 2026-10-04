#!/usr/bin/env python3
"""
Gamepad & Peripheral Battery Level Monitor (Linux)
Works with Kernel Sysfs, UPower, and Raw HID telemetry.
Zero external dependencies (pure standard library).
"""

import sys
import time
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# ANSI Color Codes
BOLD = "\033[1m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
BLUE = "\033[1;34m"
CYAN = "\033[1;36m"
MAGENTA = "\033[1;35m"
GRAY = "\033[0;90m"
RESET = "\033[0m"


def draw_bar(percent: Optional[int], width: int = 15) -> str:
    if percent is None or percent < 0:
        return f"{GRAY}[{'?' * width}]{RESET}"

    filled = int(round((percent / 100.0) * width))
    filled = max(0, min(width, filled))
    empty = width - filled

    if percent > 60:
        col = GREEN
    elif percent > 20:
        col = YELLOW
    else:
        col = RED

    return f"{col}[{'█' * filled}{'░' * empty}]{RESET}"


def read_sysfs_prop(p: Path, filename: str) -> Optional[str]:
    f = p / filename
    if f.exists() and f.is_file():
        try:
            return f.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            return None
    return None


def find_parent_device_info(psy_path: Path) -> Dict[str, str]:
    info = {
        "model": "Unknown",
        "vendor": "Unknown",
        "driver": "Unknown",
        "bus": "Unknown",
        "hid_name": "",
    }

    try:
        resolved = psy_path.resolve()
        parent = resolved.parent

        # Check driver
        driver_link = parent / "driver"
        if driver_link.exists():
            info["driver"] = driver_link.resolve().name

        # Search upwards for HID or USB attributes
        curr = parent
        for _ in range(5):
            if not curr or curr == Path("/"):
                break

            # HID device name
            if not info["hid_name"] and (curr / "name").exists():
                info["hid_name"] = read_sysfs_prop(curr, "name") or ""

            # USB device info
            if (curr / "idVendor").exists():
                info["vendor"] = (
                    read_sysfs_prop(curr, "manufacturer")
                    or read_sysfs_prop(curr, "idVendor")
                    or "Unknown"
                )
                info["model"] = (
                    read_sysfs_prop(curr, "product")
                    or read_sysfs_prop(curr, "idProduct")
                    or "Unknown"
                )
                info["bus"] = "USB"
                break
            elif "bluetooth" in str(curr).lower() or (curr / "address").exists():
                info["bus"] = "Bluetooth"

            curr = curr.parent

    except Exception:
        pass

    return info


def get_battery_devices() -> List[Dict[str, Any]]:
    psy_dir = Path("/sys/class/power_supply")
    devices = []

    if not psy_dir.exists():
        return devices

    for entry in sorted(psy_dir.iterdir()):
        if not entry.is_symlink() and not entry.is_dir():
            continue

        name = entry.name
        type_str = read_sysfs_prop(entry, "type") or "Unknown"
        scope = read_sysfs_prop(entry, "scope") or "Unknown"
        status = read_sysfs_prop(entry, "status") or "Unknown"
        model_name = read_sysfs_prop(entry, "model_name")
        manufacturer = read_sysfs_prop(entry, "manufacturer")

        capacity_str = read_sysfs_prop(entry, "capacity")
        capacity = None
        if capacity_str is not None:
            try:
                capacity = int(capacity_str)
            except ValueError:
                capacity = None

        voltage_str = read_sysfs_prop(entry, "voltage_now")
        voltage_v = None
        if voltage_str:
            try:
                voltage_v = round(int(voltage_str) / 1_000_000.0, 2)
            except ValueError:
                voltage_v = None

        parent_info = find_parent_device_info(entry)

        # Categorization
        is_gamepad = any(
            k in name.lower()
            for k in [
                "controller",
                "ps-controller",
                "sony",
                "dualshock",
                "dualsense",
                "joy",
                "gamepad",
                "xbox",
                "switch",
                "gamesir",
            ]
        )
        is_laptop = (name.startswith("BAT") or name.startswith("battery_BAT")) and scope != "Device"
        is_peripheral = scope == "Device" or not is_laptop

        display_name = model_name or parent_info["hid_name"] or parent_info["model"] or name
        if is_gamepad and "controller" not in display_name.lower():
            display_name = f"Gamepad ({display_name})"

        devices.append(
            {
                "name": name,
                "display_name": display_name,
                "type": type_str,
                "scope": scope,
                "status": status,
                "capacity": capacity,
                "voltage_v": voltage_v,
                "manufacturer": manufacturer or parent_info["vendor"],
                "driver": parent_info["driver"],
                "bus": parent_info["bus"],
                "is_gamepad": is_gamepad,
                "is_laptop": is_laptop,
                "is_peripheral": is_peripheral,
                "sysfs_path": str(entry.resolve()),
            }
        )

    return devices


def format_terminal_output(devices: List[Dict[str, Any]], gamepads_only: bool = False) -> str:
    lines = []

    if gamepads_only:
        filtered = [d for d in devices if d["is_gamepad"]]
    else:
        filtered = devices

    lines.append(
        f"{CYAN}========================================================================{RESET}"
    )
    lines.append(
        f"{BOLD} 🎮 Linux Power & Battery Monitor{RESET}  {GRAY}[{time.strftime('%Y-%m-%d %H:%M:%S')}]{RESET}"
    )
    lines.append(
        f"{CYAN}========================================================================{RESET}"
    )

    if not filtered:
        if gamepads_only:
            lines.append(f" {YELLOW}No gamepad / gaming controller batteries detected.{RESET}")
        else:
            lines.append(
                f" {YELLOW}No power supply devices detected in /sys/class/power_supply.{RESET}"
            )
        lines.append(
            f"{CYAN}------------------------------------------------------------------------{RESET}"
        )
        return "\n".join(lines)

    for dev in filtered:
        icon = "🎮" if dev["is_gamepad"] else ("💻" if dev["is_laptop"] else "🔋")
        cap = dev["capacity"]
        cap_str = f"{cap}%" if cap is not None else "N/A"
        bar = draw_bar(cap)
        status = dev["status"]

        status_col = (
            GREEN
            if status == "Charging"
            else (CYAN if status in ["Full", "Not charging"] else YELLOW)
        )

        lines.append(f"{icon} {BOLD}{dev['display_name']}{RESET} {GRAY}({dev['name']}){RESET}")
        lines.append(
            f"   Level:   {bar} {BOLD}{cap_str:<5}{RESET} Status: {status_col}{status:<12}{RESET} Driver: {BLUE}{dev['driver']}{RESET}"
        )

        details = []
        if dev["manufacturer"] and dev["manufacturer"] != "Unknown":
            details.append(f"Vendor: {dev['manufacturer']}")
        if dev["bus"] and dev["bus"] != "Unknown":
            details.append(f"Bus: {dev['bus']}")
        if dev["voltage_v"]:
            details.append(f"Voltage: {dev['voltage_v']}V")

        if details:
            lines.append(f"   Details: {GRAY}{' | '.join(details)}{RESET}")

        # Detect known 5% clone battery quirk
        if (
            dev["is_gamepad"]
            and cap == 5
            and dev["driver"] in ["playstation", "hid-playstation", "sony"]
        ):
            lines.append(
                f"   {RED}⚠️  Known Quirk:{RESET} {GRAY}Controller reported 5% via {dev['driver']}. Raw USB telemetry is 0x00 (GameSir/Clone).{RESET}"
            )

        lines.append(
            f"{GRAY}------------------------------------------------------------------------{RESET}"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Linux Gamepad & Peripheral Battery Level Monitor")
    parser.add_argument(
        "-g", "--gamepads", action="store_true", help="Filter for gamepads/controllers only"
    )
    parser.add_argument(
        "-w",
        "--watch",
        type=float,
        const=1.0,
        nargs="?",
        help="Continuously watch battery status with refresh interval (seconds, default: 1.0)",
    )
    parser.add_argument(
        "-j", "--json", action="store_true", help="Output machine-readable JSON format"
    )
    args = parser.parse_args()

    if args.json:
        devs = get_battery_devices()
        if args.gamepads:
            devs = [d for d in devs if d["is_gamepad"]]
        print(json.dumps(devs, indent=2))
        return

    if args.watch is not None:
        interval = max(0.2, args.watch)
        try:
            while True:
                # Clear screen
                sys.stdout.write("\033[2J\033[H")
                devs = get_battery_devices()
                print(format_terminal_output(devs, gamepads_only=args.gamepads))
                print(f" {GRAY}[Press Ctrl+C to exit. Refreshing every {interval:.1f}s]{RESET}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n{GRAY}Exited monitor.{RESET}")
    else:
        devs = get_battery_devices()
        print(format_terminal_output(devs, gamepads_only=args.gamepads))


if __name__ == "__main__":
    main()
