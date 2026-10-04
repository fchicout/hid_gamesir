#!/usr/bin/env bash
# Helper script to load hid-gamesir and rebind the active controller

set -e

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run with sudo: sudo ./scripts/load_and_test.sh"
    exit 1
fi

echo "[*] Compiling module if needed..."
make -C "${REPO_ROOT}"

echo "[*] Inserting hid-gamesir.ko..."
rmmod hid-gamesir 2>/dev/null || true
insmod "${REPO_ROOT}/hid-gamesir.ko"

# Find active GameSir / Sony device node
DEV_NODE=""
for dev_path in /sys/bus/hid/devices/0003:054C:09CC.*; do
    if [ -e "${dev_path}" ]; then
        DEV_NODE=$(basename "${dev_path}")
        break
    fi
done

if [ -n "$DEV_NODE" ]; then
    echo "[*] Found active controller node: $DEV_NODE"
    if [ -d "/sys/bus/hid/drivers/playstation" ]; then
        echo "$DEV_NODE" > /sys/bus/hid/drivers/playstation/unbind 2>/dev/null || true
    fi
    if [ -d "/sys/bus/hid/drivers/hid-gamesir" ]; then
        echo "$DEV_NODE" > /sys/bus/hid/drivers/hid-gamesir/bind 2>/dev/null || true
    fi
    echo "[+] Controller rebound to hid-gamesir!"
else
    echo "[!] No active 054C:09CC device found. Please replug the controller."
fi

echo "[*] Checking dmesg output:"
dmesg | tail -n 15 | grep -i "gamesir" || dmesg | tail -n 10
