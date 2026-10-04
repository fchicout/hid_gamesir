# `hid_gamesir` - Linux Kernel HID Driver for GameSir Controllers

[![CI & Quality Gates](https://github.com/fchicout/hid_gamesir/actions/workflows/ci.yml/badge.svg)](https://github.com/fchicout/hid_gamesir/actions/workflows/ci.yml)
[![License: GPL-2.0](https://img.shields.io/badge/License-GPL_2.0-blue.svg)](LICENSE)
[![SemVer](https://img.shields.io/badge/semver-0.1.0-blue)](https://semver.org)

An out-of-tree Linux Kernel module and DKMS package providing dedicated hardware handling, battery gauge fixes, and telemetry handling for **GameSir** / **Guangzhou Chicken Run Network Technology Co., Ltd.** controllers.

---

## 📌 Problem Background: The "5% Battery" Anomaly

Many GameSir multi-platform controllers (e.g., Nova, Nova Lite, T4 Pro, T4 Cyclone, G7) identify over USB using Sony's Vendor and Product IDs (`054c:09cc`, DualShock 4 CUH-ZCT2x) to ensure broad compatibility with games and game engines.

However:
1. Genuine DualShock 4 controllers transmit battery gauge telemetry (0–10 / 0–100%) in the lower nibble of byte offset 30 in report `0x01`.
2. GameSir firmware leaves this byte set to `0x00` in standard USB operation.
3. The upstream Linux kernel driver `hid-playstation` (`drivers/hid/hid-playstation.c`) calculates:
   $$\text{Capacity} = \min((\text{raw\_level} \times 10) + 5, 100)$$
   When $\text{raw\_level} = 0$, this formula permanently evaluates to **`5%`**.
4. The kernel `power_supply` subsystem and `UPower` continuously flag a false **"Critical Low Battery"** alarm on desktop environments (GNOME, KDE, Steam).

---

## 🎯 Solution Architecture

`hid-gamesir` sits as a specialized Linux HID driver:
- **Device Identification:** Matches `054c:09cc`, but inspects `hdev->name` and USB descriptors for `"Guangzhou Chicken Run"` or `"GameSir"`. Genuine Sony DualShock 4 controllers are yielded back to `hid-playstation`.
- **Battery Management:** Suppresses false low-battery nodes and isolates GameSir-specific telemetry.
- **DKMS Integration:** Automatically rebuilds on kernel updates.

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

### Method 2: Manual Out-of-Tree Build

```bash
# Build module for currently running kernel
make

# Test load kernel module
sudo insmod hid-gamesir.ko

# Inspect module log
sudo dmesg | grep hid-gamesir

# Unload
sudo rmmod hid-gamesir
```

---

## 🎮 GameSir Cyclone 2 Hardware Mapping & Back Paddles (L4 / R4)

The **GameSir Cyclone 2** features two programmable back paddles (**L4** and **R4**).

### 1. On-Board Hardware Quick-Mapping (No Software Needed)
- **Map Single Button:** Hold **`M` + `L4`** (or **`M` + `R4`**) for 2–3s until the indicator LED blinks $\rightarrow$ press target button (e.g. `A`, `B`, `X`, `Y`, `LB`, `RB`, `L3`, `R3`, `LT`, `RT`, D-pad) $\rightarrow$ press **`L4`** to save.
- **Record Macro Sequence:** Hold **`M` + `L4`** until blinking $\rightarrow$ press desired button combo in sequence $\rightarrow$ press **`L4`** to save.
- **Clear Mapping:** Hold **`M` + `L4`** until blinking $\rightarrow$ press **`L4`** immediately with no other buttons.

### 2. Diagnostic & Testing Utilities
```bash
# Interactive 60 FPS Graphical HUD (Pygame GUI)
./tools/gamepad-gui-tester.py

# Live Gamepad & Paddle Input Tester (Visual ASCII HUD)
./tools/gamepad-input-tester.py

# Multi-Platform Mode Detector (PS4 / Xbox / Switch - Live Watch Mode)
./tools/gamepad-mode-detect.py --watch

# Live Battery Level & Telemetry Monitor
./tools/gamepad-battery.py --gamepads
```

---

## 🛡️ CI & Quality Gates (Forgejo / Actions)

Automated quality gates are enforced across all branches and pull requests via [`.github/workflows/ci.yml`](.github/workflows/ci.yml) / [`.forgejo/workflows/ci.yml`](.forgejo/workflows/ci.yml):

- **🎨 Code Style & Formatting:** Linux Kernel style compliance via `clang-format` (`src/`), `shellcheck` (`scripts/`), and `ruff` (`tools/`).
- **🔒 Static Analysis & SAST:** Security scans and defect detection via `cppcheck`, `flawfinder`, and `bandit`.
- **🧪 Unit & Telemetry Testing:** Automated `unittest` test suites covering protocol math, CLI parameters, and state logic.
- **⚙️ Kernel Matrix Build:** Out-of-tree build validation and DKMS metadata verification across Linux kernel headers.

---

## 🌿 Development & Versioning

- **Semantic Versioning:** Follows [SemVer 2.0.0](https://semver.org/).
- **Conventional Commits:** All commits follow atomic `feat:`, `fix:`, `docs:`, `ci:`, `chore:`.
- **Kernel Style Guide:** Code formatted adhering to Linux kernel coding conventions via [`.clang-format`](.clang-format).

---

## 📜 License

Licensed under the **GNU General Public License v2.0 (GPL-2.0)** to match Linux Kernel upstream compatibility. See [LICENSE](LICENSE) for details.
