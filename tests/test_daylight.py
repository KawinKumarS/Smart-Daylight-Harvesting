"""Unit tests for the Smart Daylight Harvesting engine."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from backend.daylight_controller import DaylightEngine


class TestDaylightEngine(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = DaylightEngine(log_dir=Path(self._tmp.name))

    def tearDown(self) -> None:
        self.engine.shutdown()
        self._tmp.cleanup()

    def test_bright_daylight_dims_led_to_zero(self) -> None:
        self.engine.update_control({
            "mode": "AUTO",
            "target_lux": 500,
            "sim_weather": "custom",
            "sim_custom_lux": 850,
            "rated_watts": 20.0,
        })
        # Let simulator converge
        for _ in range(12):
            time.sleep(0.25)
        state = self.engine.get_state()
        t = state["telemetry"]
        self.assertIsNotNone(t)
        self.assertGreater(t["lux"], 650.0)
        self.assertEqual(t["led_pwm"], 0)
        self.assertAlmostEqual(t["power_w"], 0.0, places=2)
        self.assertAlmostEqual(t["saved_w"], 20.0, places=2)
        self.assertAlmostEqual(t["energy_saved_pct"], 100.0, places=1)

    def test_dark_room_raises_led_output(self) -> None:
        self.engine.update_control({
            "mode": "AUTO",
            "target_lux": 500,
            "sim_weather": "custom",
            "sim_custom_lux": 0,
            "rated_watts": 12.0,
        })
        for _ in range(28):
            time.sleep(0.25)
            t = self.engine.get_state()["telemetry"]
            if t and t["led_pct"] > 90.0:
                break
        t = self.engine.get_state()["telemetry"]
        self.assertIsNotNone(t)
        self.assertLess(t["lux"], 40.0)
        self.assertGreater(t["led_pct"], 85.0)
        self.assertAlmostEqual(t["power_w"] + t["saved_w"], 12.0, places=1)

    def test_manual_override_sets_exact_percentage(self) -> None:
        self.engine.update_control({
            "manual_pct": 40.0,
            "rated_watts": 10.0,
        })
        for _ in range(14):
            time.sleep(0.25)
        t = self.engine.get_state()["telemetry"]
        self.assertIsNotNone(t)
        self.assertEqual(t["mode"], "MANUAL")
        self.assertAlmostEqual(t["led_pct"], 40.0, delta=1.5)
        self.assertAlmostEqual(t["power_w"], 4.0, delta=0.2)

    def test_reset_stats_clears_history(self) -> None:
        time.sleep(0.6)
        self.engine.reset_stats()
        state = self.engine.get_state()
        self.assertEqual(len(state["history"]), 0)


if __name__ == "__main__":
    unittest.main()
