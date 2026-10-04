#!/usr/bin/env python3
"""
Real-Time Visual Gamepad Input, IMU & Paddle Tester (Linux)
Supports Linux hidraw, evdev (/dev/input/event*), and jsdev (/dev/input/js*) APIs.
Displays a pixel-perfect ASCII dashboard featuring:
  - Gamepad Buttons & Sticks
  - 6-Axis Motion Sensor (3-Axis Gyroscope + 3-Axis Accelerometer)
  - Multi-Touch Capacitive Touchpad (Coordinates & Click)
  - Analog Hall-Effect Triggers
  - Real-Time Battery & Charging Telemetry
  - L4/R4 Back Paddle Remap & Detection
"""

import sys
import os
import re
import glob
import struct
import select
import time
import argparse
import fcntl
import array
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any

# ANSI Escape Colors
BOLD = "\033[1m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[1;36m"
RED = "\033[1;31m"
BLUE = "\033[1;34m"
MAGENTA = "\033[1;35m"
GRAY = "\033[0;90m"
WHITE_ON_GREEN = "\033[1;37;42m"
RESET = "\033[0m"
CLEAR_SCREEN = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

# Linux Input Event Types & Codes
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03

BTN_SOUTH = 0x130          # A / Cross
BTN_EAST = 0x131           # B / Circle
BTN_NORTH = 0x133          # X / Triangle
BTN_WEST = 0x134           # Y / Square
BTN_TL = 0x136             # L1 / LB
BTN_TR = 0x137             # R1 / RB
BTN_TL2 = 0x138            # L2
BTN_TR2 = 0x139            # R2
BTN_SELECT = 0x13a         # Select / Share
BTN_START = 0x13b          # Start / Options
BTN_MODE = 0x13c           # Home / PS / M
BTN_THUMBL = 0x13d         # L3
BTN_THUMBR = 0x13e         # R3
BTN_TRIGGER_HAPPY1 = 0x2c0 # L4 / M1 Paddle
BTN_TRIGGER_HAPPY2 = 0x2c1 # R4 / M2 Paddle

ABS_X = 0x00
ABS_Y = 0x01
ABS_Z = 0x02
ABS_RX = 0x03
ABS_RY = 0x04
ABS_RZ = 0x05
ABS_HAT0X = 0x10
ABS_HAT0Y = 0x11

JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80

def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences to compute exact visible string width."""
    return re.sub(r'\033\[[0-9;]*[a-zA-Z]', '', text)

def pad_line(content: str, width: int = 74) -> str:
    """Wrap content inside a rigid box line with exact character padding."""
    vis_len = len(strip_ansi(content))
    pad = max(0, width - vis_len)
    return "│ " + content + (" " * pad) + " │"

def get_device_name(dev_path: str) -> str:
    """Query human-readable device name via evdev ioctl or sysfs."""
    try:
        if "event" in dev_path:
            fd = os.open(dev_path, os.O_RDONLY | os.O_NONBLOCK)
            buf = array.array('B', [0] * 256)
            fcntl.ioctl(fd, 0x80ff4506, buf, True)
            os.close(fd)
            name = buf.tobytes().split(b'\x00')[0].decode('utf-8', errors='ignore').strip()
            if name:
                return name
    except Exception:
        pass

    node_name = os.path.basename(os.path.realpath(dev_path))
    name_file = Path(f"/sys/class/input/{node_name}/device/name")
    if name_file.exists():
        try:
            return name_file.read_text().strip()
        except Exception:
            pass

    return os.path.basename(dev_path)

def list_devices() -> List[Dict[str, Any]]:
    """Enumerate all available gamepad device nodes."""
    devices = []
    seen_realpaths = set()

    for p in sorted(glob.glob("/dev/hidraw*")):
        real = os.path.realpath(p)
        if real in seen_realpaths:
            continue
        seen_realpaths.add(real)
        readable = os.access(p, os.R_OK)
        # Check if Chicken Run / GameSir
        sys_name = Path(f"/sys/class/hidraw/{os.path.basename(p)}/device/uevent")
        desc = "HIDRAW Device"
        if sys_name.exists():
            content = sys_name.read_text()
            if "Chicken Run" in content or "054C:09CC" in content:
                desc = "GameSir / DualShock 4 (Direct HID Telemetry)"
        if "GameSir" in desc or "Chicken Run" in desc or "DualShock" in desc:
            devices.append({
                "path": p,
                "realpath": real,
                "type": "hidraw",
                "name": desc,
                "readable": readable
            })

    for p in sorted(glob.glob("/dev/input/by-id/*event-joystick*") + glob.glob("/dev/input/by-id/*joystick*")):
        real = os.path.realpath(p)
        if real in seen_realpaths:
            continue
        seen_realpaths.add(real)
        readable = os.access(p, os.R_OK)
        dev_type = "evdev" if "event" in real else "jsdev"
        name = get_device_name(p)
        devices.append({
            "path": p,
            "realpath": real,
            "type": dev_type,
            "name": name,
            "readable": readable
        })

    return devices

def select_best_device() -> Optional[Dict[str, Any]]:
    devs = list_devices()
    if not devs:
        return None

    # Prefer hidraw for full 6-axis IMU + Touchpad + Battery telemetry
    hidraw_devs = [d for d in devs if d["readable"] and d["type"] == "hidraw"]
    if hidraw_devs:
        return hidraw_devs[0]

    # Fallback to evdev
    evdev_devs = [d for d in devs if d["readable"] and d["type"] == "evdev"]
    if evdev_devs:
        return evdev_devs[0]

    readable = [d for d in devs if d["readable"]]
    if readable:
        return readable[0]

    return devs[0]

class GamepadState:
    def __init__(self):
        # Buttons
        self.buttons = {
            "A": False, "B": False, "X": False, "Y": False,
            "L1": False, "R1": False, "L2": False, "R2": False,
            "SELECT": False, "START": False, "MODE": False,
            "L3": False, "R3": False,
            "L4": False, "R4": False,
            "TOUCH_CLICK": False
        }
        # Sticks & Triggers
        self.left_x = 0.0
        self.left_y = 0.0
        self.right_x = 0.0
        self.right_y = 0.0
        self.trigger_l = 0.0
        self.trigger_r = 0.0
        self.dpad_x = 0
        self.dpad_y = 0

        # 6-Axis IMU (Motion Sensors)
        self.gyro_x = 0
        self.gyro_y = 0
        self.gyro_z = 0
        self.accel_x = 0
        self.accel_y = 0
        self.accel_z = 0

        # Capacitive Touchpad
        self.touch_active = False
        self.touch_x = 0
        self.touch_y = 0
        self.touch2_active = False
        self.touch2_x = 0
        self.touch2_y = 0

        # Battery & Status
        self.battery_pct = 0
        self.battery_charging = False
        self.last_event_str = "Listening for inputs & telemetry..."
        self.event_count = 0

def draw_hud(state: GamepadState, dev_info: Dict[str, Any]):
    BOX_WIDTH = 74

    def btn_tag(label: str, active: bool, fixed_len: Optional[int] = None) -> str:
        text = label
        if fixed_len:
            text = f"{label:^{fixed_len}}"
        if active:
            return f"{WHITE_ON_GREEN} {text} {RESET}"
        else:
            return f"{GRAY}[{text}]{RESET}"

    def trigger_bar(val: float, length: int = 8) -> str:
        filled = int(round(val * length))
        filled = max(0, min(length, filled))
        empty = length - filled
        pct = int(round(val * 100))
        return f"{CYAN}[{'█' * filled}{'░' * empty}]{RESET} {pct:>3}%"

    def bat_bar(pct: int) -> str:
        filled = max(0, min(10, int(round(pct / 10.0))))
        empty = 10 - filled
        return f"[{'█' * filled}{'░' * empty}] {pct}%"

    dpad_up = state.dpad_y < 0
    dpad_down = state.dpad_y > 0
    dpad_left = state.dpad_x < 0
    dpad_right = state.dpad_x > 0

    lines = []
    lines.append(f"{CYAN}┌" + "─" * (BOX_WIDTH + 2) + "┐" + RESET)
    lines.append(pad_line(f"{BOLD}🎮 GameSir Cyclone 2 Live Input & Telemetry Tester{RESET}  {GRAY}(Events: {state.event_count}){RESET}", BOX_WIDTH))
    lines.append(pad_line(f"{BLUE}Device:{RESET} {BOLD}{dev_info.get('name', 'Unknown')}{RESET}", BOX_WIDTH))
    lines.append(pad_line(f"{BLUE}Node:  {RESET} {dev_info.get('path')} {GRAY}(Backend: {dev_info.get('type').upper()}){RESET}", BOX_WIDTH))
    lines.append(f"{CYAN}├" + "─" * (BOX_WIDTH + 2) + "┤" + RESET)
    
    # Triggers & Bumpers
    lt_str = f"LT: {btn_tag('L2', state.buttons['L2'])} {trigger_bar(state.trigger_l, 8)}"
    rt_str = f"RT: {btn_tag('R2', state.buttons['R2'])} {trigger_bar(state.trigger_r, 8)}"
    lines.append(pad_line(f"{lt_str}                    {rt_str}", BOX_WIDTH))
    
    lb_str = f"LB: {btn_tag('L1', state.buttons['L1'])}"
    rb_str = f"RB: {btn_tag('R1', state.buttons['R1'])}"
    lines.append(pad_line(f"{lb_str}                                     {rb_str}", BOX_WIDTH))
    
    lines.append(pad_line("", BOX_WIDTH))

    # Face Buttons and D-Pad Layout
    lines.append(pad_line("       D-PAD               SYSTEM BUTTONS            ACTION BUTTONS", BOX_WIDTH))
    lines.append(pad_line(f"        {btn_tag('▲', dpad_up, 1)}              {btn_tag('BACK', state.buttons['SELECT'])}  {btn_tag('M/PS', state.buttons['MODE'])}  {btn_tag('START', state.buttons['START'])}            {btn_tag('Y', state.buttons['Y'], 1)}", BOX_WIDTH))
    lines.append(pad_line(f"     {btn_tag('◀', dpad_left, 1)}     {btn_tag('▶', dpad_right, 1)}                                      {btn_tag('X', state.buttons['X'], 1)}     {btn_tag('B', state.buttons['B'], 1)}", BOX_WIDTH))
    lines.append(pad_line(f"        {btn_tag('▼', dpad_down, 1)}                                                   {btn_tag('A', state.buttons['A'], 1)}", BOX_WIDTH))
    
    lines.append(pad_line("", BOX_WIDTH))

    # Analog Sticks
    stick_l = f"STICK L: (X:{state.left_x:+0.2f}, Y:{state.left_y:+0.2f}) {btn_tag('L3', state.buttons['L3'])}"
    stick_r = f"STICK R: (X:{state.right_x:+0.2f}, Y:{state.right_y:+0.2f}) {btn_tag('R3', state.buttons['R3'])}"
    lines.append(pad_line(f"{stick_l}         {stick_r}", BOX_WIDTH))

    lines.append(pad_line("", BOX_WIDTH))

    # Back Paddles (L4 / R4)
    l4_btn = btn_tag("L4 / M1", state.buttons["L4"])
    r4_btn = btn_tag("R4 / M2", state.buttons["R4"])
    lines.append(pad_line(f"   [REAR PADDLE L4]                                  [REAR PADDLE R4]", BOX_WIDTH))
    lines.append(pad_line(f"      {l4_btn}                                          {r4_btn}", BOX_WIDTH))

    lines.append(f"{CYAN}├" + "─" * (BOX_WIDTH + 2) + "┤" + RESET)
    
    # 6-Axis IMU (Motion Telemetry)
    lines.append(pad_line(f"{BOLD}🧭 6-Axis Motion Sensor (IMU):{RESET}", BOX_WIDTH))
    gyro_str = f"GYRO:  (X:{state.gyro_x:+05d}, Y:{state.gyro_y:+05d}, Z:{state.gyro_z:+05d})"
    accel_str = f"ACCEL: (X:{state.accel_x:+05d}, Y:{state.accel_y:+05d}, Z:{state.accel_z:+05d})"
    lines.append(pad_line(f"  {CYAN}{gyro_str}{RESET}    {MAGENTA}{accel_str}{RESET}", BOX_WIDTH))

    # Capacitive Touchpad
    touch_click_tag = btn_tag("CLICK", state.buttons["TOUCH_CLICK"])
    f1_pos = f"(X:{state.touch_x:04d}, Y:{state.touch_y:04d})" if state.touch_active else "(INACTIVE)"
    f2_pos = f"(X:{state.touch2_x:04d}, Y:{state.touch2_y:04d})" if state.touch2_active else "(INACTIVE)"
    lines.append(pad_line(f"{BOLD}👆 Capacitive Touchpad:{RESET} {touch_click_tag}  F1: {YELLOW}{f1_pos:<15}{RESET} F2: {GRAY}{f2_pos}{RESET}", BOX_WIDTH))

    # Battery & Power
    if state.battery_pct == 100 and state.battery_charging:
        bat_str = "[██████████] 100% (⚡ Wired USB Power)"
    else:
        bat_str = f"{bat_bar(state.battery_pct)} ({'⚡ Charging' if state.battery_charging else '🔋 Discharging'})"
    lines.append(pad_line(f"{BOLD}🔋 Battery Status:{RESET} {GREEN}{bat_str}{RESET}", BOX_WIDTH))

    lines.append(f"{CYAN}├" + "─" * (BOX_WIDTH + 2) + "┤" + RESET)
    lines.append(pad_line(f"{BOLD}Last Event:{RESET} {YELLOW}{state.last_event_str}{RESET}", BOX_WIDTH))
    lines.append(f"{CYAN}├" + "─" * (BOX_WIDTH + 2) + "┤" + RESET)
    lines.append(pad_line(f"{BOLD}💡 Cyclone 2 Hardware Paddle Remap Guide:{RESET}", BOX_WIDTH))
    lines.append(pad_line(f"   1. Hold {BOLD}M{RESET} + Press {BOLD}L4{RESET} (or {BOLD}R4{RESET}) until Home LED blinks.", BOX_WIDTH))
    lines.append(pad_line(f"   2. Press target button (A, B, X, Y, LB, RB, L3, R3, etc.)", BOX_WIDTH))
    lines.append(pad_line(f"   3. Press {BOLD}L4{RESET} (or {BOLD}R4{RESET}) again to save. It now emits that button!", BOX_WIDTH))
    lines.append(pad_line(f"   {GRAY}[Press Ctrl+C to exit tester]{RESET}", BOX_WIDTH))
    lines.append(f"{CYAN}└" + "─" * (BOX_WIDTH + 2) + "┘" + RESET)

    sys.stdout.write(CLEAR_SCREEN + "\n".join(lines) + "\n")
    sys.stdout.flush()

def run_hidraw_tester(dev_info: Dict[str, Any]):
    """Process full-speed 64-byte HID report packets (inputs + IMU + touchpad + battery)."""
    dev_path = dev_info["realpath"]
    fd = os.open(dev_path, os.O_RDONLY | os.O_NONBLOCK)
    state = GamepadState()

    DPAD_MAP = {
        0: (0, -1),   # Up
        1: (1, -1),   # Up-Right
        2: (1, 0),    # Right
        3: (1, 1),    # Down-Right
        4: (0, 1),    # Down
        5: (-1, 1),   # Down-Left
        6: (-1, 0),   # Left
        7: (-1, -1),  # Up-Left
        8: (0, 0),    # Released
    }

    sys.stdout.write(HIDE_CURSOR)
    draw_hud(state, dev_info)

    try:
        while True:
            r, _, _ = select.select([fd], [], [], 0.05)
            if fd in r:
                while True:
                    try:
                        data = os.read(fd, 64)
                        if len(data) < 30 or data[0] != 0x01:
                            break
                        state.event_count += 1

                        # Sticks (0..255 -> -1.0..1.0)
                        state.left_x = (data[1] - 128) / 128.0
                        state.left_y = (data[2] - 128) / 128.0
                        state.right_x = (data[3] - 128) / 128.0
                        state.right_y = (data[4] - 128) / 128.0

                        # D-Pad (Hat)
                        hat = data[5] & 0x0f
                        state.dpad_x, state.dpad_y = DPAD_MAP.get(hat, (0, 0))

                        # Face Buttons
                        state.buttons["X"] = bool(data[5] & 0x10)
                        state.buttons["A"] = bool(data[5] & 0x20)
                        state.buttons["B"] = bool(data[5] & 0x40)
                        state.buttons["Y"] = bool(data[5] & 0x80)

                        # Shoulder & Auxiliary Buttons
                        state.buttons["L1"] = bool(data[6] & 0x01)
                        state.buttons["R1"] = bool(data[6] & 0x02)
                        state.buttons["L2"] = bool(data[6] & 0x04)
                        state.buttons["R2"] = bool(data[6] & 0x08)
                        state.buttons["SELECT"] = bool(data[6] & 0x10)
                        state.buttons["START"] = bool(data[6] & 0x20)
                        state.buttons["L3"] = bool(data[6] & 0x40)
                        state.buttons["R3"] = bool(data[6] & 0x80)

                        # System Buttons & Touch Click
                        state.buttons["MODE"] = bool(data[7] & 0x01)
                        state.buttons["TOUCH_CLICK"] = bool(data[7] & 0x02)

                        # Analog Triggers (0..255)
                        state.trigger_l = data[8] / 255.0
                        state.trigger_r = data[9] / 255.0

                        # 6-Axis IMU (Motion Sensors)
                        state.gyro_x, state.gyro_y, state.gyro_z = struct.unpack_from('<hhh', data, 13)
                        state.accel_x, state.accel_y, state.accel_z = struct.unpack_from('<hhh', data, 19)

                        # Battery Telemetry (Cyclone 2 on USB VBUS is fully powered)
                        bat_byte = data[30]
                        bat_level = bat_byte & 0x0f
                        if bat_level == 0:
                            state.battery_pct = 100
                            state.battery_charging = True
                        else:
                            state.battery_pct = min(bat_level * 10, 100)
                            state.battery_charging = bool(bat_byte & 0x10)

                        # Capacitive Touchpad
                        if len(data) >= 42:
                            state.touch_active = not bool(data[35] & 0x80)
                            state.touch_x = data[36] | ((data[37] & 0x0f) << 8)
                            state.touch_y = (data[37] >> 4) | (data[38] << 4)

                            state.touch2_active = not bool(data[39] & 0x80)
                            state.touch2_x = data[40] | ((data[41] & 0x0f) << 8)
                            state.touch2_y = (data[41] >> 4) | (data[42] << 4)

                        state.last_event_str = f"Report 0x01 | IMU G:({state.gyro_x:+04d},{state.gyro_y:+04d},{state.gyro_z:+04d}) | Bat: {state.battery_pct}%"

                    except BlockingIOError:
                        break
                    except Exception:
                        break

                draw_hud(state, dev_info)
    finally:
        os.close(fd)
        sys.stdout.write(SHOW_CURSOR)
        print("\nExited input tester.")

def run_evdev_tester(dev_info: Dict[str, Any]):
    """Process live Linux evdev (struct input_event) packets."""
    dev_path = dev_info["realpath"]
    fd = os.open(dev_path, os.O_RDONLY | os.O_NONBLOCK)
    state = GamepadState()

    EVENT_FORMAT = "qqHHi"
    EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

    KEY_MAP = {
        BTN_SOUTH: "A",
        BTN_EAST: "B",
        BTN_NORTH: "X",
        BTN_WEST: "Y",
        BTN_TL: "L1",
        BTN_TR: "R1",
        BTN_TL2: "L2",
        BTN_TR2: "R2",
        BTN_SELECT: "SELECT",
        BTN_START: "START",
        BTN_MODE: "MODE",
        BTN_THUMBL: "L3",
        BTN_THUMBR: "R3",
        BTN_TRIGGER_HAPPY1: "L4",
        BTN_TRIGGER_HAPPY2: "R4",
    }

    sys.stdout.write(HIDE_CURSOR)
    draw_hud(state, dev_info)

    try:
        while True:
            r, _, _ = select.select([fd], [], [], 0.05)
            if fd in r:
                while True:
                    try:
                        data = os.read(fd, EVENT_SIZE)
                        if len(data) < EVENT_SIZE:
                            break
                        _, _, ev_type, code, value = struct.unpack(EVENT_FORMAT, data)
                        state.event_count += 1

                        if ev_type == EV_KEY:
                            pressed = (value == 1)
                            b_name = KEY_MAP.get(code, f"KEY_0x{code:03x}")
                            if b_name in state.buttons:
                                state.buttons[b_name] = pressed
                            state.last_event_str = f"Button {b_name} {'PRESSED' if pressed else 'RELEASED'} (evdev code 0x{code:x}/{code})"

                        elif ev_type == EV_ABS:
                            if code == ABS_X:
                                state.left_x = (value - 128) / 128.0 if value <= 255 else value / 32767.0
                            elif code == ABS_Y:
                                state.left_y = (value - 128) / 128.0 if value <= 255 else value / 32767.0
                            elif code == ABS_RX or code == ABS_Z:
                                if code == ABS_RX:
                                    state.right_x = (value - 128) / 128.0 if value <= 255 else value / 32767.0
                                else:
                                    state.trigger_l = value / 255.0 if value <= 255 else max(0.0, (value + 32768) / 65535.0)
                            elif code == ABS_RY or code == ABS_RZ:
                                if code == ABS_RY:
                                    state.right_y = (value - 128) / 128.0 if value <= 255 else value / 32767.0
                                else:
                                    state.trigger_r = value / 255.0 if value <= 255 else max(0.0, (value + 32768) / 65535.0)
                            elif code == ABS_HAT0X:
                                state.dpad_x = value
                            elif code == ABS_HAT0Y:
                                state.dpad_y = value

                            state.last_event_str = f"Axis 0x{code:x} = {value}"

                    except BlockingIOError:
                        break
                    except Exception:
                        break

                draw_hud(state, dev_info)
    finally:
        os.close(fd)
        sys.stdout.write(SHOW_CURSOR)
        print("\nExited input tester.")

def main():
    parser = argparse.ArgumentParser(description="Real-Time Visual Gamepad Input, IMU & Telemetry Tester")
    parser.add_argument("-d", "--device", help="Path to /dev/hidraw*, /dev/input/event*, or /dev/input/js* device node", default=None)
    parser.add_argument("-l", "--list", action="store_true", help="List all detected gamepad/joystick devices")
    parser.add_argument("--hidraw", action="store_true", help="Force hidraw backend mode (full IMU + Touchpad + Battery)")
    parser.add_argument("--evdev", action="store_true", help="Force evdev backend mode")
    args = parser.parse_args()

    if args.list:
        devs = list_devices()
        print(f"\n{BOLD}Detected Input & HID Devices ({len(devs)}):{RESET}")
        print("------------------------------------------------------------------------")
        for idx, d in enumerate(devs, 1):
            access_str = f"{GREEN}Readable{RESET}" if d["readable"] else f"{RED}Permission Denied (run with sudo){RESET}"
            print(f" {idx}. {BOLD}{d['name']}{RESET}")
            print(f"    Path:    {d['path']} -> {d['realpath']}")
            print(f"    Type:    {d['type'].upper()}  |  Access: {access_str}")
        print("------------------------------------------------------------------------\n")
        return

    dev_info = None
    if args.device:
        target = args.device
        real = os.path.realpath(target)
        dev_type = "hidraw" if "hidraw" in real else ("evdev" if "event" in real else "jsdev")
        if args.hidraw:
            dev_type = "hidraw"
        elif args.evdev:
            dev_type = "evdev"
        dev_info = {
            "path": target,
            "realpath": real,
            "type": dev_type,
            "name": get_device_name(target),
            "readable": os.access(target, os.R_OK)
        }
    else:
        dev_info = select_best_device()

    if not dev_info:
        print(f"{RED}Error: No gamepad device found under /dev/hidraw* or /dev/input/.{RESET}")
        print("Ensure the controller is connected via USB.")
        sys.exit(1)

    if not dev_info["readable"]:
        print(f"{RED}Error: Permission denied accessing {dev_info['path']}.{RESET}")
        print(f"Please run with sudo or check udev permissions:")
        print(f"  sudo python3 tools/gamepad-input-tester.py -d {dev_info['path']}")
        sys.exit(1)

    if dev_info["type"] == "hidraw":
        run_hidraw_tester(dev_info)
    else:
        run_evdev_tester(dev_info)

if __name__ == "__main__":
    main()
