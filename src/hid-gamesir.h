/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * HID driver for GameSir / Guangzhou Chicken Run controllers
 *
 * Copyright (c) 2026 Francisco Chicout
 */

#ifndef _HID_GAMESIR_H
#define _HID_GAMESIR_H

#include <linux/hid.h>
#include <linux/input.h>
#include <linux/spinlock.h>
#include <linux/types.h>

#define USB_VENDOR_ID_SONY_SPOOFED 0x054c
#define USB_DEVICE_ID_SONY_DS4_CUH_ZCT2 0x09cc

/* Quirk flags */
#define GAMESIR_QUIRK_NO_BATTERY_GAUGE BIT(0)
#define GAMESIR_QUIRK_FORCE_INPUT_PARSE BIT(1)

/**
 * struct gamesir_device - Driver private data for GameSir controllers
 * @hdev: Pointer to underlying HID device
 * @gamepad: Registered Linux input_dev for standard gamepad events
 * @quirks: Device quirk bitmask
 * @lock: Spinlock protecting telemetry and state updates
 * @battery_capacity: Normalized capacity (-1 if unsupported/invalid)
 * @battery_status: Power supply status enum
 */
struct gamesir_device {
	struct hid_device *hdev;
	struct input_dev *gamepad;
	u32 quirks;
	spinlock_t lock;
	int battery_capacity;
	int battery_status;
};

#endif /* _HID_GAMESIR_H */
