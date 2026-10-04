// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Linux HID Driver for GameSir / Guangzhou Chicken Run Controllers
 *
 * Fixes battery gauge bugs, input anomalies, and mode-switching quirks
 * for GameSir controllers emulating Sony DualShock 4 or Xbox protocols.
 * Full Linux input_dev subsystem integration for W3C Gamepad & SDL2/SDL3.
 *
 * Copyright (c) 2026 Francisco Chicout
 */

#include "hid-gamesir.h"
#include <linux/device.h>
#include <linux/hid.h>
#include <linux/input.h>
#include <linux/module.h>
#include <linux/power_supply.h>
#include <linux/slab.h>
#include <linux/string.h>

#define DRIVER_NAME "hid-gamesir"
#define DRIVER_VERSION "0.1.0"

static bool disable_battery_node = true;
module_param(disable_battery_node, bool, 0644);
MODULE_PARM_DESC(disable_battery_node,
		 "Disable registering the faulty power_supply battery node (default: true)");

static const char *const gamesir_signatures[] = {
    "Chicken Run",
    "GameSir",
    "GAMESIR",
    "gamesir",
};

/* DualShock 4 D-pad Hat switch lookup tables */
static const int dpad_hat_x[] = {0, 1, 1, 1, 0, -1, -1, -1, 0};
static const int dpad_hat_y[] = {-1, -1, 0, 1, 1, 1, 0, -1, 0};

static bool is_gamesir_device(const struct hid_device *hdev)
{
	size_t i;

	if (!hdev || !hdev->name[0])
		return false;

	for (i = 0; i < ARRAY_SIZE(gamesir_signatures); i++) {
		if (strstr(hdev->name, gamesir_signatures[i]))
			return true;
	}

	return false;
}

static int gamesir_setup_input_dev(struct gamesir_device *gdev)
{
	struct hid_device *hdev = gdev->hdev;
	struct input_dev *input;
	int ret;

	input = devm_input_allocate_device(&hdev->dev);
	if (!input)
		return -ENOMEM;

	input->name = "GameSir Wireless Controller (Gamepad)";
	input->phys = hdev->phys;
	input->uniq = hdev->uniq;
	input->id.bustype = hdev->bus;
	input->id.vendor = hdev->vendor;
	input->id.product = hdev->product;
	input->id.version = hdev->version;
	input->dev.parent = &hdev->dev;
	input_set_drvdata(input, gdev);

	/* Set Standard Linux Gamepad Key / Button Capabilities */
	input_set_capability(input, EV_KEY, BTN_SOUTH);
	input_set_capability(input, EV_KEY, BTN_EAST);
	input_set_capability(input, EV_KEY, BTN_NORTH);
	input_set_capability(input, EV_KEY, BTN_WEST);
	input_set_capability(input, EV_KEY, BTN_TL);
	input_set_capability(input, EV_KEY, BTN_TR);
	input_set_capability(input, EV_KEY, BTN_TL2);
	input_set_capability(input, EV_KEY, BTN_TR2);
	input_set_capability(input, EV_KEY, BTN_SELECT);
	input_set_capability(input, EV_KEY, BTN_START);
	input_set_capability(input, EV_KEY, BTN_MODE);
	input_set_capability(input, EV_KEY, BTN_THUMBL);
	input_set_capability(input, EV_KEY, BTN_THUMBR);

	/* Back Paddle Capabilities (Cyclone 2 L4 / R4) */
	input_set_capability(input, EV_KEY, BTN_TRIGGER_HAPPY1);
	input_set_capability(input, EV_KEY, BTN_TRIGGER_HAPPY2);

	/* Set Standard Gamepad Analog Axis Capabilities (0..255) */
	input_set_abs_params(input, ABS_X, 0, 255, 0, 0);
	input_set_abs_params(input, ABS_Y, 0, 255, 0, 0);
	input_set_abs_params(input, ABS_Z, 0, 255, 0, 0);
	input_set_abs_params(input, ABS_RZ, 0, 255, 0, 0);
	input_set_abs_params(input, ABS_RX, 0, 255, 0, 0);
	input_set_abs_params(input, ABS_RY, 0, 255, 0, 0);
	input_set_abs_params(input, ABS_HAT0X, -1, 1, 0, 0);
	input_set_abs_params(input, ABS_HAT0Y, -1, 1, 0, 0);

	ret = input_register_device(input);
	if (ret) {
		hid_err(hdev, "Failed to register input device: %d\n", ret);
		return ret;
	}

	gdev->gamepad = input;
	return 0;
}

// cppcheck-suppress constParameterCallback
static int gamesir_raw_event(struct hid_device *hdev, struct hid_report *report, u8 *data, int size)
{
	struct gamesir_device *gdev = hid_get_drvdata(hdev);

	if (!gdev || !data || size < 10)
		return 0;

	/*
	 * Process DualShock 4 emulation report (Report ID 0x01, USB):
	 * data[1]: Left Stick X (0..255)
	 * data[2]: Left Stick Y (0..255)
	 * data[3]: Right Stick X (0..255)
	 * data[4]: Right Stick Y (0..255)
	 * data[5]: Buttons (Square, Cross, Circle, Triangle) + D-pad Hat (bits 0-3)
	 * data[6]: Buttons (L1, R1, L2, R2, Select/Share, Start/Options, L3, R3)
	 * data[7]: Buttons (PS Home, Touchpad Click)
	 * data[8]: Analog L2 Trigger (0..255)
	 * data[9]: Analog R2 Trigger (0..255)
	 * data[30]: Battery telemetry byte
	 */
	if (data[0] == 0x01 && gdev->gamepad) {
		struct input_dev *input = gdev->gamepad;
		u8 hat_val = data[5] & 0x0F;
		int hat0x = 0;
		int hat0y = 0;

		if (hat_val <= 7) {
			hat0x = dpad_hat_x[hat_val];
			hat0y = dpad_hat_y[hat_val];
		}

		/* Thumbsticks */
		input_report_abs(input, ABS_X, data[1]);
		input_report_abs(input, ABS_Y, data[2]);
		input_report_abs(input, ABS_Z, data[3]);
		input_report_abs(input, ABS_RZ, data[4]);

		/* Analog Triggers */
		input_report_abs(input, ABS_RX, data[8]);
		input_report_abs(input, ABS_RY, data[9]);

		/* D-Pad Hat */
		input_report_abs(input, ABS_HAT0X, hat0x);
		input_report_abs(input, ABS_HAT0Y, hat0y);

		/* Action Buttons */
		input_report_key(input, BTN_WEST, !!(data[5] & BIT(4)));
		input_report_key(input, BTN_SOUTH, !!(data[5] & BIT(5)));
		input_report_key(input, BTN_EAST, !!(data[5] & BIT(6)));
		input_report_key(input, BTN_NORTH, !!(data[5] & BIT(7)));

		/* Shoulder & Auxiliary Buttons */
		input_report_key(input, BTN_TL, !!(data[6] & BIT(0)));
		input_report_key(input, BTN_TR, !!(data[6] & BIT(1)));
		input_report_key(input, BTN_TL2, !!(data[6] & BIT(2)));
		input_report_key(input, BTN_TR2, !!(data[6] & BIT(3)));
		input_report_key(input, BTN_SELECT, !!(data[6] & BIT(4)));
		input_report_key(input, BTN_START, !!(data[6] & BIT(5)));
		input_report_key(input, BTN_THUMBL, !!(data[6] & BIT(6)));
		input_report_key(input, BTN_THUMBR, !!(data[6] & BIT(7)));

		/* System Buttons */
		input_report_key(input, BTN_MODE, !!(data[7] & BIT(0)));

		/*
		 * GameSir Cyclone 2 repurposes the DualShock 4 Touchpad Click bit
		 * (data[7] bit 1) for rear paddle interactions (L4/R4) since Cyclone 2
		 * features hardware back paddles rather than a front touchpad.
		 * Expose directly as native gamepad paddle button (BTN_TRIGGER_HAPPY1).
		 */
		input_report_key(input, BTN_TRIGGER_HAPPY1, !!(data[7] & BIT(1)));

		input_sync(input);

		/* Battery telemetry handling */
		if (size >= 33) {
			unsigned long flags;
			const u8 bat_byte = data[30];
			const u8 bat_level = bat_byte & 0x0F;

			spin_lock_irqsave(&gdev->lock, flags);
			if (bat_level == 0 && (gdev->quirks & GAMESIR_QUIRK_NO_BATTERY_GAUGE)) {
				/* Controller is operating on wired 5V USB power */
				gdev->battery_capacity = 100;
				gdev->battery_status = POWER_SUPPLY_STATUS_FULL;
			} else {
				gdev->battery_capacity = min_t(int, bat_level * 10, 100);
				gdev->battery_status = (bat_byte & 0x10)
							   ? POWER_SUPPLY_STATUS_CHARGING
							   : POWER_SUPPLY_STATUS_DISCHARGING;
			}
			spin_unlock_irqrestore(&gdev->lock, flags);
		}
	}

	return 0;
}

static int gamesir_probe(struct hid_device *hdev, const struct hid_device_id *id)
{
	struct gamesir_device *gdev;
	int ret;

	/*
	 * Verify if this device is genuinely a GameSir / Guangzhou Chicken Run product.
	 * If not, yield to official hid-playstation or hid-sony drivers.
	 */
	if (!is_gamesir_device(hdev)) {
		hid_dbg(hdev, "Non-GameSir device ignored by " DRIVER_NAME "\n");
		return -ENODEV;
	}

	hid_info(hdev, "Claiming GameSir Controller: %s (VID: 0x%04x, PID: 0x%04x)\n", hdev->name,
		 hdev->vendor, hdev->product);

	gdev = devm_kzalloc(&hdev->dev, sizeof(*gdev), GFP_KERNEL);
	if (!gdev)
		return -ENOMEM;

	gdev->hdev = hdev;
	gdev->quirks = (u32)id->driver_data;
	gdev->battery_capacity = -1;
	gdev->battery_status = POWER_SUPPLY_STATUS_UNKNOWN;
	spin_lock_init(&gdev->lock);
	hid_set_drvdata(hdev, gdev);

	ret = hid_parse(hdev);
	if (ret) {
		hid_err(hdev, "Failed to parse HID report descriptor: %d\n", ret);
		return ret;
	}

	/* Start hardware with HIDRAW and driver handling */
	ret = hid_hw_start(hdev, HID_CONNECT_HIDRAW);
	if (ret) {
		hid_err(hdev, "Failed to start HID hardware: %d\n", ret);
		return ret;
	}

	/* Register standardized Linux input_dev */
	ret = gamesir_setup_input_dev(gdev);
	if (ret) {
		hid_hw_stop(hdev);
		return ret;
	}

	ret = hid_hw_open(hdev);
	if (ret) {
		hid_err(hdev, "Failed to open HID hardware: %d\n", ret);
		hid_hw_stop(hdev);
		return ret;
	}

	hid_info(hdev,
		 "GameSir controller initialized successfully with standard Gamepad input (v%s)\n",
		 DRIVER_VERSION);
	return 0;
}

static void gamesir_remove(struct hid_device *hdev)
{
	hid_hw_close(hdev);
	hid_hw_stop(hdev);
	hid_info(hdev, "GameSir controller removed\n");
}

static const struct hid_device_id gamesir_devices[] = {
    /* GameSir / Guangzhou Chicken Run controllers spoofing Sony DualShock 4 */
    {HID_USB_DEVICE(USB_VENDOR_ID_SONY_SPOOFED, USB_DEVICE_ID_SONY_DS4_CUH_ZCT2),
     .driver_data = GAMESIR_QUIRK_NO_BATTERY_GAUGE},
    {}};
MODULE_DEVICE_TABLE(hid, gamesir_devices);

static struct hid_driver gamesir_driver = {
    .name = DRIVER_NAME,
    .id_table = gamesir_devices,
    .probe = gamesir_probe,
    .remove = gamesir_remove,
    .raw_event = gamesir_raw_event,
};

module_hid_driver(gamesir_driver);

MODULE_AUTHOR("Francisco Chicout");
MODULE_DESCRIPTION("Linux HID driver for GameSir / Guangzhou Chicken Run Controllers");
MODULE_VERSION(DRIVER_VERSION);
MODULE_LICENSE("GPL");
