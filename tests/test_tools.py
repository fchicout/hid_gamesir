"""
Automated unit tests for GameSir tools & utilities.
Tests CLI parsing, telemetry math, ANSI rendering, and device detection logic.
"""

import sys
import unittest
import importlib.util
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestGamepadTools(unittest.TestCase):
    def test_battery_draw_bar(self):
        battery_mod = load_module("gamepad_battery", "tools/gamepad-battery.py")
        bar_full = battery_mod.draw_bar(100, width=10)
        self.assertIn("█", bar_full)
        self.assertTrue(len(battery_mod.draw_bar(None)) > 0)
        self.assertTrue(len(battery_mod.draw_bar(0)) > 0)
        self.assertTrue(len(battery_mod.draw_bar(50)) > 0)

    def test_input_tester_alignment(self):
        tester_mod = load_module("gamepad_input_tester", "tools/gamepad-input-tester.py")

        raw_str = "\033[1;32mActive Button\033[0m"
        clean_str = tester_mod.strip_ansi(raw_str)
        self.assertEqual(clean_str, "Active Button")

        line1 = tester_mod.pad_line("Short line", width=74)
        line2 = tester_mod.pad_line("\033[1;34mColored line\033[0m with more text", width=74)

        self.assertEqual(len(tester_mod.strip_ansi(line1)), 78)  # 74 + "│ " + " │"
        self.assertEqual(len(tester_mod.strip_ansi(line2)), 78)
        self.assertEqual(len(tester_mod.strip_ansi(line1)), len(tester_mod.strip_ansi(line2)))

    def test_mode_detector_modes(self):
        mode_mod = load_module("gamepad_mode_detect", "tools/gamepad-mode-detect.py")
        self.assertIn(("054c", "09cc"), mode_mod.KNOWN_MODES)
        self.assertIn(("045e", "028e"), mode_mod.KNOWN_MODES)
        self.assertIn(("057e", "2009"), mode_mod.KNOWN_MODES)

        ds4_info = mode_mod.KNOWN_MODES[("054c", "09cc")]
        self.assertIn("PlayStation 4", ds4_info["mode"])

    def test_input_tester_state(self):
        tester_mod = load_module("gamepad_input_tester", "tools/gamepad-input-tester.py")
        state = tester_mod.GamepadState()
        self.assertFalse(state.buttons["A"])
        self.assertFalse(state.buttons["L4"])
        self.assertEqual(state.left_x, 0.0)
        self.assertEqual(state.trigger_l, 0.0)


if __name__ == "__main__":
    unittest.main()
