#!/usr/bin/env python3
"""
GameSir Cyclone 2 Interactive Graphical Input, IMU & Telemetry Tester (Pygame GUI)
Provides a rich 60 FPS graphical HUD visualizing:
  - GameSir Cyclone 2 Controller with animated button presses and thumbstick vectors
  - Hall-Effect Analog Triggers (LT/RT) with smooth linear meters
  - L4 (M1) & R4 (M2) Back Paddle detection
  - 6-Axis Motion Sensor (3-Axis Gyroscope + 3-Axis Accelerometer with tilt bubble)
  - Capacitive Touchpad & Click coordinate mapping
  - Real-time Battery Percentage & Charging status
  - Active Kernel Driver & Hardware Mode detection
"""

import sys
import os
import math
import time
import glob
import struct
import select
import array
import fcntl
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

try:
    import pygame
except ImportError:
    print("Error: pygame is required. Please install with: pip install pygame-ce")
    sys.exit(1)

# Color Palette (Cyberpunk / Modern Dark)
BG_COLOR = (18, 20, 28)
PANEL_BG = (28, 32, 45)
PANEL_BORDER = (45, 52, 72)
ACCENT_CYAN = (0, 229, 255)
ACCENT_GREEN = (0, 230, 118)
ACCENT_YELLOW = (255, 215, 64)
ACCENT_RED = (255, 82, 82)
ACCENT_MAGENTA = (224, 64, 251)
ACCENT_BLUE = (68, 138, 255)
TEXT_WHITE = (245, 247, 250)
TEXT_MUTED = (140, 150, 170)
BUTTON_INACTIVE = (42, 48, 66)
BUTTON_ACTIVE = (0, 230, 118)
STICK_BG = (22, 26, 38)
STICK_BORDER = (60, 70, 95)
STICK_CAP = (55, 65, 88)
STICK_CAP_ACTIVE = (0, 229, 255)

class GamepadTelemetry:
    def __init__(self):
        self.lock = threading.Lock()
        # Buttons
        self.buttons = {
            "A": False, "B": False, "X": False, "Y": False,
            "L1": False, "R1": False, "L2": False, "R2": False,
            "SELECT": False, "START": False, "MODE": False,
            "L3": False, "R3": False,
            "L4": False, "R4": False,
            "TOUCH_CLICK": False
        }
        # Sticks (-1.0 to 1.0)
        self.left_x = 0.0
        self.left_y = 0.0
        self.right_x = 0.0
        self.right_y = 0.0
        # Triggers (0.0 to 1.0)
        self.trigger_l = 0.0
        self.trigger_r = 0.0
        # D-Pad (-1, 0, 1)
        self.dpad_x = 0
        self.dpad_y = 0
        # 6-Axis IMU
        self.gyro_x = 0
        self.gyro_y = 0
        self.gyro_z = 0
        self.accel_x = 0
        self.accel_y = 0
        self.accel_z = 0
        # Touchpad
        self.touch_active = False
        self.touch_x = 0
        self.touch_y = 0
        # Battery & Status
        self.battery_pct = 0
        self.battery_charging = False
        self.event_count = 0
        self.poll_rate_hz = 0
        self.active_driver = "Checking..."
        self.device_name = "Detecting Gamepad..."
        self.device_node = "None"
        self.connected = False

def query_bound_driver() -> str:
    """Find active Linux kernel driver bound to 054C:09CC or GameSir."""
    for p in glob.glob("/sys/bus/hid/devices/*054C:09CC*"):
        driver_link = Path(p) / "driver"
        if driver_link.exists():
            return driver_link.resolve().name
    for p in glob.glob("/sys/bus/usb/devices/*"):
        path = Path(p)
        mf_f = path / "manufacturer"
        if mf_f.exists() and "Chicken Run" in mf_f.read_text():
            for child in path.glob("*:*"):
                d = child / "driver"
                if d.exists():
                    return d.resolve().name
    return "Unknown / Generic"

def hidraw_reader_thread(telemetry: GamepadTelemetry, stop_event: threading.Event):
    """Continuously poll HIDRAW device for high-speed 64-byte telemetry."""
    DPAD_MAP = {
        0: (0, -1), 1: (1, -1), 2: (1, 0), 3: (1, 1),
        4: (0, 1), 5: (-1, 1), 6: (-1, 0), 7: (-1, -1), 8: (0, 0)
    }

    last_sec = time.time()
    packet_counter = 0

    while not stop_event.is_set():
        # Find hidraw node
        hidraw_path = None
        for p in sorted(glob.glob("/dev/hidraw*")):
            sys_name = Path(f"/sys/class/hidraw/{os.path.basename(p)}/device/uevent")
            if sys_name.exists():
                txt = sys_name.read_text()
                if "Chicken Run" in txt or "054C:09CC" in txt or "054c:09cc" in txt:
                    if os.access(p, os.R_OK):
                        hidraw_path = p
                        break

        if not hidraw_path:
            # Fallback to /dev/hidraw1 if exists
            if os.path.exists("/dev/hidraw1") and os.access("/dev/hidraw1", os.R_OK):
                hidraw_path = "/dev/hidraw1"

        if not hidraw_path:
            with telemetry.lock:
                telemetry.connected = False
                telemetry.active_driver = query_bound_driver()
            time.sleep(0.5)
            continue

        try:
            fd = os.open(hidraw_path, os.O_RDONLY | os.O_NONBLOCK)
            with telemetry.lock:
                telemetry.connected = True
                telemetry.device_node = hidraw_path
                telemetry.device_name = "GameSir Cyclone 2 (DualShock 4 Mode)"
                telemetry.active_driver = query_bound_driver()

            while not stop_event.is_set():
                r, _, _ = select.select([fd], [], [], 0.1)
                if fd in r:
                    while True:
                        try:
                            data = os.read(fd, 64)
                            if len(data) < 30 or data[0] != 0x01:
                                break

                            packet_counter += 1
                            now = time.time()
                            if now - last_sec >= 1.0:
                                with telemetry.lock:
                                    telemetry.poll_rate_hz = packet_counter
                                packet_counter = 0
                                last_sec = now

                            with telemetry.lock:
                                telemetry.event_count += 1
                                # Sticks
                                telemetry.left_x = (data[1] - 128) / 128.0
                                telemetry.left_y = (data[2] - 128) / 128.0
                                telemetry.right_x = (data[3] - 128) / 128.0
                                telemetry.right_y = (data[4] - 128) / 128.0

                                # D-Pad
                                hat = data[5] & 0x0f
                                telemetry.dpad_x, telemetry.dpad_y = DPAD_MAP.get(hat, (0, 0))

                                # Face Buttons
                                telemetry.buttons["X"] = bool(data[5] & 0x10)
                                telemetry.buttons["A"] = bool(data[5] & 0x20)
                                telemetry.buttons["B"] = bool(data[5] & 0x40)
                                telemetry.buttons["Y"] = bool(data[5] & 0x80)

                                # Shoulders & Auxiliary
                                telemetry.buttons["L1"] = bool(data[6] & 0x01)
                                telemetry.buttons["R1"] = bool(data[6] & 0x02)
                                telemetry.buttons["L2"] = bool(data[6] & 0x04)
                                telemetry.buttons["R2"] = bool(data[6] & 0x08)
                                telemetry.buttons["SELECT"] = bool(data[6] & 0x10)
                                telemetry.buttons["START"] = bool(data[6] & 0x20)
                                telemetry.buttons["L3"] = bool(data[6] & 0x40)
                                telemetry.buttons["R3"] = bool(data[6] & 0x80)

                                # System & Touch Click / Paddles
                                telemetry.buttons["MODE"] = bool(data[7] & 0x01)
                                touch_click = bool(data[7] & 0x02)
                                telemetry.buttons["TOUCH_CLICK"] = touch_click

                                # Cyclone 2 maps Touch Click bit to unmapped L4/R4 paddles
                                telemetry.buttons["L4"] = touch_click

                                # Triggers
                                telemetry.trigger_l = data[8] / 255.0
                                telemetry.trigger_r = data[9] / 255.0

                                # 6-Axis IMU
                                telemetry.gyro_x, telemetry.gyro_y, telemetry.gyro_z = struct.unpack_from('<hhh', data, 13)
                                telemetry.accel_x, telemetry.accel_y, telemetry.accel_z = struct.unpack_from('<hhh', data, 19)

                                # Battery Telemetry (Cyclone 2 on USB VBUS is fully powered)
                                bat_byte = data[30]
                                bat_level = bat_byte & 0x0f
                                if bat_level == 0:
                                    telemetry.battery_pct = 100
                                    telemetry.battery_charging = True
                                else:
                                    telemetry.battery_pct = min(bat_level * 10, 100)
                                    telemetry.battery_charging = bool(bat_byte & 0x10)

                                # Touchpad
                                if len(data) >= 38:
                                    telemetry.touch_active = not bool(data[35] & 0x80)
                                    telemetry.touch_x = data[36] | ((data[37] & 0x0f) << 8)
                                    telemetry.touch_y = (data[37] >> 4) | (data[38] << 4)

                        except BlockingIOError:
                            break
                        except Exception:
                            break

            os.close(fd)
        except Exception:
            time.sleep(0.5)

def draw_rounded_panel(surface, rect, color=PANEL_BG, border_color=PANEL_BORDER, radius=12, border_width=2):
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border_width > 0:
        pygame.draw.rect(surface, border_color, rect, width=border_width, border_radius=radius)

def main():
    pygame.init()
    pygame.display.set_caption("GameSir Cyclone 2 - Live Input & Telemetry GUI")
    
    WIDTH, HEIGHT = 1040, 740
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont("DejaVu Sans,Arial,Helvetica", 20, bold=True)
    font_sub = pygame.font.SysFont("DejaVu Sans,Arial,Helvetica", 14, bold=True)
    font_body = pygame.font.SysFont("DejaVu Sans,Arial,Helvetica", 12)
    font_btn = pygame.font.SysFont("DejaVu Sans,Arial,Helvetica", 13, bold=True)
    font_hud = pygame.font.SysFont("Monospace,Courier", 11)

    telemetry = GamepadTelemetry()
    stop_event = threading.Event()
    reader_thread = threading.Thread(target=hidraw_reader_thread, args=(telemetry, stop_event), daemon=True)
    reader_thread.start()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # Read snapshot
        with telemetry.lock:
            btns = telemetry.buttons.copy()
            lx, ly = telemetry.left_x, telemetry.left_y
            rx, ry = telemetry.right_x, telemetry.right_y
            tl, tr = telemetry.trigger_l, telemetry.trigger_r
            dpad_x, dpad_y = telemetry.dpad_x, telemetry.dpad_y
            gx, gy, gz = telemetry.gyro_x, telemetry.gyro_y, telemetry.gyro_z
            ax, ay, az = telemetry.accel_x, telemetry.accel_y, telemetry.accel_z
            bat_pct = telemetry.battery_pct
            bat_charging = telemetry.battery_charging
            driver_name = telemetry.active_driver
            dev_node = telemetry.device_node
            poll_hz = telemetry.poll_rate_hz
            connected = telemetry.connected

        screen.fill(BG_COLOR)

        # ---------------------------------------------------------------------
        # 1. TOP HEADER PANEL (Device, Driver, Mode, Status)
        # ---------------------------------------------------------------------
        draw_rounded_panel(screen, pygame.Rect(20, 16, WIDTH - 40, 70))
        
        # Title
        title_surf = font_title.render("🎮 GameSir Cyclone 2  |  Hardware Telemetry & Input Tester", True, TEXT_WHITE)
        screen.blit(title_surf, (36, 26))

        # Status Badges
        status_color = ACCENT_GREEN if connected else ACCENT_RED
        status_text = "CONNECTED (ACTIVE)" if connected else "DISCONNECTED / WAITING"
        pygame.draw.circle(screen, status_color, (44, 62), 6)
        lbl_status = font_sub.render(status_text, True, status_color)
        screen.blit(lbl_status, (56, 54))

        # Driver Badge
        driver_col = ACCENT_CYAN if "gamesir" in driver_name.lower() else (ACCENT_BLUE if "playstation" in driver_name.lower() else ACCENT_YELLOW)
        lbl_drv = font_body.render(f"Driver: {driver_name.upper()}", True, driver_col)
        screen.blit(lbl_drv, (280, 56))

        # Node & Polling
        lbl_node = font_body.render(f"Node: {dev_node}  ({poll_hz} Hz)", True, TEXT_MUTED)
        screen.blit(lbl_node, (520, 56))

        # Battery Gauge (Top Right)
        bat_col = ACCENT_GREEN if bat_pct > 30 else (ACCENT_YELLOW if bat_pct > 10 else ACCENT_RED)
        bat_rect = pygame.Rect(WIDTH - 220, 32, 180, 36)
        draw_rounded_panel(screen, bat_rect, color=(20, 24, 34), border_color=bat_col, radius=8, border_width=1)
        
        if bat_pct == 100 and bat_charging:
            bat_txt = font_sub.render("⚡ USB Powered (100%)", True, ACCENT_GREEN)
        else:
            charge_icon = "⚡ " if bat_charging else "🔋 "
            bat_txt = font_sub.render(f"{charge_icon}{bat_pct}% {'Charging' if bat_charging else 'Discharging'}", True, bat_col)
        screen.blit(bat_txt, (WIDTH - 208, 42))

        # ---------------------------------------------------------------------
        # 2. CENTER: CYCLONE 2 CONTROLLER SCHEMATIC
        # ---------------------------------------------------------------------
        ctrl_panel = pygame.Rect(20, 100, 640, 420)
        draw_rounded_panel(screen, ctrl_panel)

        # Controller Shell Background (Vector silhouette)
        shell_color = (38, 44, 60)
        pygame.draw.polygon(screen, shell_color, [
            (100, 240), (140, 140), (280, 130), (380, 130), (520, 140), (560, 240),
            (590, 430), (530, 490), (450, 440), (380, 390), (280, 390), (210, 440),
            (130, 490), (70, 430)
        ])
        pygame.draw.polygon(screen, (55, 65, 88), [
            (100, 240), (140, 140), (280, 130), (380, 130), (520, 140), (560, 240),
            (590, 430), (530, 490), (450, 440), (380, 390), (280, 390), (210, 440),
            (130, 490), (70, 430)
        ], width=2)

        # Triggers (LT / RT) at top
        lt_bar_rect = pygame.Rect(120, 110, 100, 18)
        rt_bar_rect = pygame.Rect(440, 110, 100, 18)
        draw_rounded_panel(screen, lt_bar_rect, color=(20, 24, 34), radius=4, border_width=1)
        draw_rounded_panel(screen, rt_bar_rect, color=(20, 24, 34), radius=4, border_width=1)
        if tl > 0:
            pygame.draw.rect(screen, ACCENT_CYAN, pygame.Rect(121, 111, int(98 * tl), 16), border_radius=3)
        if tr > 0:
            pygame.draw.rect(screen, ACCENT_CYAN, pygame.Rect(441, 111, int(98 * tr), 16), border_radius=3)
        screen.blit(font_btn.render(f"LT {int(tl*100)}%", True, TEXT_WHITE), (130, 92))
        screen.blit(font_btn.render(f"RT {int(tr*100)}%", True, TEXT_WHITE), (500, 92))

        # Bumpers (LB / RB)
        lb_rect = pygame.Rect(140, 136, 80, 22)
        rb_rect = pygame.Rect(440, 136, 80, 22)
        draw_rounded_panel(screen, lb_rect, color=ACCENT_GREEN if btns["L1"] else BUTTON_INACTIVE, radius=6, border_width=1)
        draw_rounded_panel(screen, rb_rect, color=ACCENT_GREEN if btns["R1"] else BUTTON_INACTIVE, radius=6, border_width=1)
        screen.blit(font_btn.render("LB (L1)", True, (10, 20, 10) if btns["L1"] else TEXT_WHITE), (155, 139))
        screen.blit(font_btn.render("RB (R1)", True, (10, 20, 10) if btns["R1"] else TEXT_WHITE), (455, 139))

        # Center Touchpad / Logo Area
        touch_box = pygame.Rect(260, 150, 140, 70)
        draw_rounded_panel(screen, touch_box, color=(24, 28, 40), border_color=ACCENT_YELLOW if btns["TOUCH_CLICK"] else PANEL_BORDER, radius=8)
        screen.blit(font_sub.render("GAMESIR", True, ACCENT_YELLOW if btns["TOUCH_CLICK"] else TEXT_MUTED), (296, 165))
        lbl_pad_state = font_hud.render("[TOUCH CLICK]" if btns["TOUCH_CLICK"] else "(Click / Paddle M1/M2)", True, ACCENT_GREEN if btns["TOUCH_CLICK"] else (100, 110, 130))
        screen.blit(lbl_pad_state, (270, 192))

        # System Buttons (Back, Home/M, Start)
        def draw_pill_btn(x, y, label, active):
            r = pygame.Rect(x, y, 32, 16)
            draw_rounded_panel(screen, r, color=ACCENT_GREEN if active else BUTTON_INACTIVE, radius=4, border_width=1)
            t = font_btn.render(label, True, (10, 20, 10) if active else TEXT_WHITE)
            screen.blit(t, (x + 4, y + 1))

        draw_pill_btn(245, 235, "◀◀", btns["SELECT"])
        draw_pill_btn(385, 235, "▶▶", btns["START"])
        
        # Home / M Button (Center Circular)
        pygame.draw.circle(screen, ACCENT_YELLOW if btns["MODE"] else (45, 52, 70), (330, 245), 16)
        pygame.draw.circle(screen, ACCENT_YELLOW if btns["MODE"] else PANEL_BORDER, (330, 245), 16, width=2)
        screen.blit(font_btn.render("M", True, (10, 20, 10) if btns["MODE"] else TEXT_WHITE), (324, 236))

        # D-PAD (Left)
        dpad_cx, dpad_cy = 190, 250
        def draw_dpad_dir(dx, dy, active, label):
            r = pygame.Rect(dpad_cx + dx * 26 - 13, dpad_cy + dy * 26 - 13, 26, 26)
            draw_rounded_panel(screen, r, color=ACCENT_GREEN if active else BUTTON_INACTIVE, radius=4, border_width=1)
            txt = font_btn.render(label, True, (10, 20, 10) if active else TEXT_WHITE)
            screen.blit(txt, (r.x + 8, r.y + 5))

        draw_dpad_dir(0, -1, dpad_y < 0, "▲")
        draw_dpad_dir(0, 1, dpad_y > 0, "▼")
        draw_dpad_dir(-1, 0, dpad_x < 0, "◀")
        draw_dpad_dir(1, 0, dpad_x > 0, "▶")

        # Face Action Buttons (Right: A, B, X, Y)
        face_cx, face_cy = 475, 250
        def draw_face_btn(dx, dy, label, active, color):
            pos = (face_cx + dx * 30, face_cy + dy * 30)
            pygame.draw.circle(screen, color if active else BUTTON_INACTIVE, pos, 14)
            pygame.draw.circle(screen, color, pos, 14, width=2)
            txt = font_btn.render(label, True, (10, 20, 10) if active else color)
            screen.blit(txt, (pos[0] - 5, pos[1] - 8))

        draw_face_btn(0, -1, "Y", btns["Y"], ACCENT_YELLOW)
        draw_face_btn(1, 0, "B", btns["B"], ACCENT_RED)
        draw_face_btn(0, 1, "A", btns["A"], ACCENT_GREEN)
        draw_face_btn(-1, 0, "X", btns["X"], ACCENT_BLUE)

        # Analog Sticks (Left Stick at 230, 340; Right Stick at 430, 340)
        def draw_stick(cx, cy, sx, sy, btn_active, label):
            pygame.draw.circle(screen, STICK_BG, (cx, cy), 42)
            pygame.draw.circle(screen, STICK_BORDER, (cx, cy), 42, width=2)
            pygame.draw.line(screen, (40, 48, 66), (cx - 40, cy), (cx + 40, cy), 1)
            pygame.draw.line(screen, (40, 48, 66), (cx, cy - 40), (cx, cy + 40), 1)

            # Cap position
            cap_x = cx + int(sx * 26)
            cap_y = cy + int(sy * 26)
            cap_col = ACCENT_CYAN if btn_active else STICK_CAP
            pygame.draw.circle(screen, cap_col, (cap_x, cap_y), 20)
            pygame.draw.circle(screen, ACCENT_CYAN if btn_active else (80, 95, 125), (cap_x, cap_y), 20, width=2)
            
            # Label
            lbl = font_btn.render(label, True, (10, 20, 10) if btn_active else TEXT_WHITE)
            screen.blit(lbl, (cap_x - 8, cap_y - 8))
            coord_str = f"({sx:+0.2f}, {sy:+0.2f})"
            screen.blit(font_hud.render(coord_str, True, TEXT_MUTED), (cx - 30, cy + 48))

        draw_stick(240, 340, lx, ly, btns["L3"], "L3")
        draw_stick(420, 340, rx, ry, btns["R3"], "R3")

        # Rear Paddles (L4 & R4 on back grips)
        l4_rect = pygame.Rect(130, 440, 100, 30)
        r4_rect = pygame.Rect(430, 440, 100, 30)
        draw_rounded_panel(screen, l4_rect, color=ACCENT_GREEN if btns["L4"] else (30, 36, 50), border_color=ACCENT_GREEN if btns["L4"] else PANEL_BORDER, radius=6)
        draw_rounded_panel(screen, r4_rect, color=ACCENT_GREEN if btns["R4"] else (30, 36, 50), border_color=ACCENT_GREEN if btns["R4"] else PANEL_BORDER, radius=6)
        screen.blit(font_btn.render("REAR PADDLE L4", True, (10, 20, 10) if btns["L4"] else TEXT_WHITE), (136, 447))
        screen.blit(font_btn.render("REAR PADDLE R4", True, (10, 20, 10) if btns["R4"] else TEXT_WHITE), (436, 447))

        # ---------------------------------------------------------------------
        # 3. RIGHT PANEL: 6-AXIS IMU (GYROSCOPE & ACCELEROMETER)
        # ---------------------------------------------------------------------
        imu_panel = pygame.Rect(680, 100, 340, 270)
        draw_rounded_panel(screen, imu_panel)

        screen.blit(font_sub.render("🧭 6-Axis Motion Sensor (IMU)", True, TEXT_WHITE), (696, 114))

        # Gyroscope Readings (deg/s)
        screen.blit(font_body.render("Gyroscope (Angular Velocity):", True, ACCENT_CYAN), (696, 142))
        screen.blit(font_hud.render(f"Pitch (X): {gx:+05d}", True, TEXT_WHITE), (696, 162))
        screen.blit(font_hud.render(f"Yaw   (Y): {gy:+05d}", True, TEXT_WHITE), (806, 162))
        screen.blit(font_hud.render(f"Roll  (Z): {gz:+05d}", True, TEXT_WHITE), (916, 162))

        # Accelerometer Readings (mg)
        screen.blit(font_body.render("Accelerometer (Linear Gravity):", True, ACCENT_MAGENTA), (696, 192))
        screen.blit(font_hud.render(f"Accel X: {ax:+05d}", True, TEXT_WHITE), (696, 212))
        screen.blit(font_hud.render(f"Accel Y: {ay:+05d}", True, TEXT_WHITE), (806, 212))
        screen.blit(font_hud.render(f"Accel Z: {az:+05d}", True, TEXT_WHITE), (916, 212))

        # Tilt Bubble Level
        bubble_box = pygame.Rect(790, 240, 120, 110)
        draw_rounded_panel(screen, bubble_box, color=(20, 24, 34), radius=8)
        bx = 790 + 60 + int(max(-45, min(45, (ax / 8192.0) * 45)))
        by = 240 + 55 + int(max(-40, min(40, (ay / 8192.0) * 40)))
        pygame.draw.circle(screen, (40, 50, 70), (790 + 60, 240 + 55), 45, width=1)
        pygame.draw.circle(screen, ACCENT_CYAN, (bx, by), 10)
        screen.blit(font_hud.render("Tilt Bubble Level", True, TEXT_MUTED), (800, 335))

        # ---------------------------------------------------------------------
        # 4. RIGHT BOTTOM PANEL: CAPACITIVE TOUCHPAD TRACKER
        # ---------------------------------------------------------------------
        touch_panel = pygame.Rect(680, 390, 340, 130)
        draw_rounded_panel(screen, touch_panel)
        screen.blit(font_sub.render("👆 Capacitive Touchpad Tracker", True, TEXT_WHITE), (696, 404))
        
        touch_canvas = pygame.Rect(696, 430, 200, 75)
        draw_rounded_panel(screen, touch_canvas, color=(16, 20, 28), radius=6, border_width=1)
        
        # Touch point inside canvas (0..1920, 0..942)
        if telemetry.touch_active:
            px = 696 + int((telemetry.touch_x / 1920.0) * 200)
            py = 430 + int((telemetry.touch_y / 942.0) * 75)
            pygame.draw.circle(screen, ACCENT_YELLOW, (px, py), 6)
            screen.blit(font_hud.render(f"F1: ({telemetry.touch_x:04d}, {telemetry.touch_y:04d})", True, ACCENT_YELLOW), (910, 440))
        else:
            screen.blit(font_hud.render("F1: Inactive", True, TEXT_MUTED), (910, 440))

        screen.blit(font_hud.render(f"Click: {'ON' if btns['TOUCH_CLICK'] else 'OFF'}", True, ACCENT_GREEN if btns["TOUCH_CLICK"] else TEXT_MUTED), (910, 470))

        # ---------------------------------------------------------------------
        # 5. BOTTOM FOOTER: PADDLE & DRIVER CAPABILITY GUIDE
        # ---------------------------------------------------------------------
        footer_panel = pygame.Rect(20, 540, WIDTH - 40, 175)
        draw_rounded_panel(screen, footer_panel)

        screen.blit(font_sub.render("💡 GameSir Cyclone 2 Hardware vs Driver Architecture:", True, ACCENT_YELLOW), (36, 552))
        screen.blit(font_body.render("• In hid_gamesir driver: Back paddles (L4/R4) are mapped as native gamepad triggers (BTN_TRIGGER_HAPPY1/2).", True, TEXT_WHITE), (36, 576))
        screen.blit(font_body.render("• In hid-playstation driver: Cyclone 2 translates unmapped L4/R4 paddles as touchpad clicks (as DS4 lacks rear paddles).", True, TEXT_MUTED), (36, 596))
        screen.blit(font_body.render("• Hardware Remapping: Hold [M] + Press [L4/R4] until LED blinks -> Press target button (A, B, X, Y, LB, RB) -> Press paddle again to save.", True, TEXT_WHITE), (36, 616))
        screen.blit(font_body.render("• Press ESC or Close window to exit tester.", True, (110, 120, 140)), (36, 642))

        pygame.display.flip()
        clock.tick(60)

    stop_event.set()
    reader_thread.join(timeout=1.0)
    pygame.quit()

if __name__ == "__main__":
    main()
