import unittest

from rh56_sdk import RH56Driver
from rh56_sdk.calibration import ForceCalibration
from rh56_sdk.constants import RH56_OPEN_FRAME
from rh56_sdk.exceptions import (
    RH56BusyError,
    RH56CalibrationError,
    RH56HardwareError,
    RH56NotConnectedError,
    RH56ValidationError,
)
from rh56_sdk.registers import REG_ANGLE_SET, REG_GESTURE_FORCE_CLB


class DriverMockTests(unittest.TestCase):
    def test_mock_driver_reads_zero_feedback(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect()
        try:
            self.assertEqual(hand.read_angle(), [0, 0, 0, 0, 0, 0])
            self.assertEqual(hand.read_force(), [0, 0, 0, 0, 0, 0])
            self.assertEqual(hand.read_status(), [0, 0, 0, 0, 0, 0])
            self.assertEqual(hand.miss_count, 0)
            self.assertFalse(hand.is_stale)
        finally:
            hand.disconnect()

    def test_connect_synchronizes_command_cache_from_actual_angle(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect()
        try:
            self.assertEqual(hand._last_commanded_angle, [0, 0, 0, 0, 0, 0])
        finally:
            hand.disconnect()

    def test_mock_driver_move_to_records_last_command(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect()
        try:
            hand.move_to(RH56_OPEN_FRAME)
            self.assertIsNotNone(hand.last_command)
            self.assertEqual(hand.last_command["addr"], REG_ANGLE_SET)
            self.assertEqual(hand.last_command["data"], RH56_OPEN_FRAME)
        finally:
            hand.disconnect()

    def test_move_to_requires_connection(self) -> None:
        hand = RH56Driver("COM_MOCK")

        with self.assertRaises(RH56NotConnectedError):
            hand.move_to(RH56_OPEN_FRAME)

    def test_speed_and_force_threshold_validate_ranges(self) -> None:
        hand = RH56Driver("COM_MOCK")
        with self.assertRaises(RH56ValidationError):
            hand.set_speed([-1, 0, 0, 0, 0, 0])
        with self.assertRaises(RH56ValidationError):
            hand.set_speed([1001, 0, 0, 0, 0, 0])
        with self.assertRaises(RH56ValidationError):
            hand.set_force_threshold([True, 0, 0, 0, 0, 0])
        with self.assertRaises(RH56ValidationError):
            hand.set_force_threshold([float("inf"), 0, 0, 0, 0, 0])

    def test_clear_error_keeps_safe_stop_when_fault_remains(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect(verify=False)
        try:
            hand.read_error = lambda: [1, 0, 0, 0, 0, 0]
            hand.read_status = lambda: [0, 0, 0, 0, 0, 0]
            with self.assertRaises(RH56HardwareError):
                hand.clear_error(settle_time=0)
            self.assertTrue(hand.safe_stop)
        finally:
            hand.disconnect()

    def test_read_error_enters_safe_stop(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect(verify=False)
        try:
            hand._read_bytes = lambda addr, length: bytes([1, 0, 0, 0, 0, 0])
            self.assertEqual(hand.read_error(), [1, 0, 0, 0, 0, 0])
            self.assertTrue(hand.safe_stop)
        finally:
            hand.disconnect()

    def test_force_calibration_requires_explicit_confirmation(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect()
        try:
            with self.assertRaises(RH56CalibrationError):
                ForceCalibration(hand).run_official(wait=False)
        finally:
            hand.disconnect()

    def test_force_calibration_explicit_confirm_writes_u8_register(self) -> None:
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
            self.assertEqual(hand.last_command["width"], "u8")

            with self.assertRaises(RH56BusyError):
                hand.move_to(RH56_OPEN_FRAME)
        finally:
            hand.disconnect()

    def test_force_zero_offset_and_net_force_on_mock(self) -> None:
        hand = RH56Driver("COM_MOCK")
        hand.connect()
        try:
            calibration = ForceCalibration(hand)
            self.assertEqual(calibration.measure_baseline(samples=3), [0] * 6)
            self.assertEqual(calibration.get_net_force(), [0] * 6)
            result = calibration.validate_baseline(samples=3, tolerance=1)
            self.assertTrue(result["ok"])
            self.assertEqual(result["median"], [0] * 6)
        finally:
            hand.disconnect()


if __name__ == "__main__":
    unittest.main()
