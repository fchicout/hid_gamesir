# `hid_gamesir` - Linux Kernel HID Driver for GameSir Controllers

[![CI & Quality Gates](https://github.com/fchicout/hid_gamesir/actions/workflows/ci.yml/badge.svg)](https://github.com/fchicout/hid_gamesir/actions/workflows/ci.yml)
[![License: GPL-2.0](https://img.shields.io/badge/License-GPL_2.0-blue.svg)](LICENSE)
[![SemVer](https://img.shields.io/badge/semver-0.1.0-blue)](https://semver.org)

An out-of-tree Linux Kernel module and DKMS package providing dedicated hardware handling, battery gauge fixes, and telemetry management for **GameSir** / **Guangzhou Chicken Run Network Technology Co., Ltd.** controllers.

---

## 📌 Problem Background: The "5% Battery" Anomaly

Many GameSir multi-platform controllers (e.g., Cyclone 2, Nova, Nova Lite, T4 Pro, T4 Cyclone, G7) identify over USB using Sony's Vendor and Product IDs (`054c:09cc`, DualShock 4 CUH-ZCT2x) to ensure broad plug-and-play compatibility across games and engines.

However:
1. Genuine DualShock 4 controllers transmit battery gauge telemetry (`0` to `10` representing 0–100% capacity) in the lower nibble of byte offset 30 in report `0x01`.
2. GameSir hardware operates on direct 5V USB VBUS power when wired and leaves this telemetry byte set to `0x00`.
3. The upstream Linux kernel driver `hid-playstation` (`drivers/hid/hid-playstation.c`) calculates capacity using:
   ```text
   Capacity = min((raw_battery_level * 10) + 5, 100)
   ```
   When `raw_battery_level = 0`, this evaluates to:
   ```text
   Capacity = (0 * 10) + 5 = 5%
   ```
4. As a result, the kernel `power_supply` subsystem and desktop daemons (`UPower`, GNOME, KDE, Steam) continuously trigger a false **"Critical Low Battery (5%)"** notification for a controller that is fully powered via USB.

---

## 🎯 Solution Architecture

`hid-gamesir` provides dedicated matching and input/power handling:

```text
               USB Device Connected (VID: 0x054C, PID: 0x09CC)
                                      │
                                      ▼
                        hid-gamesir Probe Handler
                                      │
           ┌──────────────────────────┴──────────────────────────┐
           ▼                                                     ▼
  Manufacturer Match:                                   Genuine Sony Hardware:
  "Guangzhou Chicken Run" / "GameSir"                   "Sony Interactive Entertainment"
           │                                                     │
           ▼                                                     ▼
  Claimed by hid-gamesir                                Yield to hid-playstation
  ├─ Power Supply: 100% (USB VBUS)                      └─ Standard DualShock 4
  ├─ Back Paddles: Direct Button Event                     Battery & Touchpad
  └─ IMU & Gamepad Inputs Routed
```

### Key Features
- **Accurate Power Reporting:** Suppresses the `5%` bug on wired USB connections and reports `100% / USB Powered` to `power_supply` / `UPower`.
- **Back Paddle Routing (L4 / R4):** Emits standard gamepad button events (`BTN_TRIGGER_HAPPY1`) instead of creating phantom touchpad click devices.
- **Selective Driver Binding:** Inspects USB manufacturer string descriptors to claim only GameSir controllers, transparently falling back to `hid-playstation` for genuine DualShock 4 controllers.
- **DKMS Automated Builds:** Automatically compiles against new kernel releases upon system upgrades.

---

## 🛠️ Installation & Usage

### Method 1: Automatic DKMS Installation (Recommended)

```bash
git clone https://github.com/fchicout/hid_gamesir.git
cd hid_gamesir
sudo ./scripts/dkms-install.sh
```

To uninstall:
```bash
sudo ./scripts/dkms-remove.sh
```

### Method 2: Manual Out-of-Tree Build & Test

```bash
# Build kernel module against active kernel headers
make

# Insert module and rebind active controller
sudo ./scripts/load_and_test.sh

# Inspect kernel logs
sudo dmesg | grep -i "gamesir"
```

---

## 🎮 GameSir Cyclone 2 Hardware Mapping & Back Paddles (L4 / R4)

The **GameSir Cyclone 2** features two programmable rear paddles (**L4** and **R4**).

### 1. On-Board Hardware Quick-Mapping (No Software Needed)

- **Map Single Button:** Hold **`M` + `L4`** (or **`M` + `R4`**) for 2–3s until the Home LED blinks → press the target button (e.g. `A`, `B`, `X`, `Y`, `LB`, `RB`, `L3`, `R3`, `LT`, `RT`, D-pad) → press **`L4`** to save.
- **Record Macro Sequence:** Hold **`M` + `L4`** until blinking → press the desired button combination in sequence → press **`L4`** to save.
- **Clear Mapping:** Hold **`M` + `L4`** until blinking → press **`L4`** immediately with no other buttons.

---

## 🧰 Diagnostic & Testing Toolkit

The repository includes standalone diagnostic tools located in `tools/`:

### Prerequisites (Python Utilities)
```bash
pip install pygame
```

### Available Tools

| Tool | Command | Description |
| :--- | :--- | :--- |
| **GUI Tester** | `./tools/gamepad-gui-tester.py` | 60 FPS graphical HUD showing interactive button presses, stick vectors, 6-axis IMU tilt bubble level, touchpad tracker, and battery level. |
| **Input HUD** | `./tools/gamepad-input-tester.py` | Live terminal ASCII HUD displaying sticks, triggers, bumpers, D-Pad, face buttons, and rear paddles in real time. |
| **Mode Detector** | `./tools/gamepad-mode-detect.py --watch` | Real-time USB monitor showing active controller mode (PS4, Xbox 360, Switch, or Android/DirectInput). |
| **Battery Monitor** | `./tools/gamepad-battery.py --gamepads` | Queries Linux `power_supply` sysfs nodes and flags known clone telemetry quirks. |

---

## 🛡️ CI & Quality Gates (Forgejo & GitHub Actions)

All commits and pull requests are verified across 4 automated quality gates:

- **Code Linting & Style:** Linux Kernel C style verification via `clang-format` (`src/`), ShellCheck for scripts (`scripts/`), and `ruff` for Python tools (`tools/`, `tests/`).
- **Security & SAST:** Vulnerability and security analysis using `cppcheck`, `flawfinder`, and `bandit`.
- **Unit & Telemetry Testing:** `unittest` suite covering battery calculation formulas, input event mapping, and mode detection tables.
- **Kernel Build Matrix:** Out-of-tree build validation and DKMS metadata verification across Linux kernel headers.

---

## 🌿 Development & Versioning

- **Semantic Versioning:** Follows [SemVer 2.0.0](https://semver.org/).
- **Conventional Commits:** Standard atomic commit messages (`feat:`, `fix:`, `docs:`, `ci:`, `style:`, `refactor:`).
- **Code Formatting:** Configured in [`.clang-format`](.clang-format) and [`pyproject.toml`](pyproject.toml).

---

## 📜 License

Licensed under the **GNU General Public License v2.0 (GPL-2.0)** to maintain compatibility with the Linux Kernel. See [LICENSE](LICENSE) for details.

