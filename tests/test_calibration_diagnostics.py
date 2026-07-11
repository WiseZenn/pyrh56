import unittest
from pathlib import Path

from rh56_sdk import RH56Driver
from rh56_sdk.calibration import ForceCalibration
from rh56_sdk.diagnostics import RH56Diagnostics
from rh56_sdk.models import FeedbackSnapshot
from rh56_sdk.registers import REG_GESTURE_FORCE_CLB


class CalibrationDiagnosticsTests(unittest.TestCase):
    def test_force_calibration_official_command_is_separate_object(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect()
        try:
            calibration = ForceCalibration(hand)
            self.assertTrue(
                calibration.run_official(
                    wait=False,
                    timeout=0.01,
                    require_confirm=False,
                )
            )
            self.assertTrue(hand.is_calibrating)
            self.assertEqual(hand.last_command["addr"], REG_GESTURE_FORCE_CLB)
            self.assertEqual(hand.last_command["data"], [1])
        finally:
            hand.disconnect()

    def test_force_baseline_save_and_load_profile(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect()
        try:
            calibration = ForceCalibration(hand)
            self.assertEqual(calibration.measure_baseline(samples=3, interval=0), [0] * 6)
            path = Path("rh56_test_profile_tmp.json")
            try:
                calibration.save_profile(path)
                hand.force_zero_offset = [1, 1, 1, 1, 1, 1]
                loaded = calibration.load_profile(path)
            finally:
                if path.exists():
                    try:
                        path.unlink()
                    except PermissionError:
                        pass

            self.assertEqual(loaded["force_zero_offset"], [0] * 6)
            self.assertEqual(hand.force_zero_offset, [0] * 6)
        finally:
            hand.disconnect()

    def test_diagnostics_returns_typed_feedback_snapshot(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect()
        try:
            snapshot = RH56Diagnostics(hand).read_feedback_snapshot()
            self.assertIsInstance(snapshot, FeedbackSnapshot)
            self.assertEqual(snapshot.angle, (0, 0, 0, 0, 0, 0))
            self.assertEqual(snapshot.voltage, 0)
        finally:
            hand.disconnect()


if __name__ == "__main__":
    unittest.main()
