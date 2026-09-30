import math
import unittest

from rh56_sdk.exceptions import RH56ServoLimitError, RH56ValidationError
from rh56_sdk.safety import clamp_frame, normalize_u16_vector, validate_frame


class SafetyTests(unittest.TestCase):
    def test_validate_frame_accepts_safe_six_value_frame(self) -> None:
        validate_frame([1000, 1000, 1000, 1000, 700, 900])

    def test_validate_frame_rejects_wrong_length(self) -> None:
        with self.assertRaises(RH56ValidationError):
            validate_frame([1000, 1000])

    def test_validate_frame_rejects_none_and_nan(self) -> None:
        with self.assertRaises(RH56ValidationError):
            validate_frame(None)

        with self.assertRaises(RH56ValidationError):
            validate_frame([1000, 1000, 1000, 1000, math.nan, 900])

    def test_validate_frame_rejects_out_of_range_values(self) -> None:
        with self.assertRaises(RH56ServoLimitError):
            validate_frame([1001, 1000, 1000, 1000, 1000, 900])

    def test_clamp_frame_limits_values(self) -> None:
        self.assertEqual(
            clamp_frame([-1, 500, 1001, 1000, 0, 1500]),
            [0, 500, 1000, 1000, 0, 1000],
        )

    def test_u16_vector_rejects_range_bool_and_infinite_values(self) -> None:
        for values in (
            [-1, 0, 0, 0, 0, 0],
            [1001, 0, 0, 0, 0, 0],
            [True, 0, 0, 0, 0, 0],
            [math.inf, 0, 0, 0, 0, 0],
        ):
            with self.assertRaises(RH56ValidationError):
                normalize_u16_vector(values, name="speed")


if __name__ == "__main__":
    unittest.main()
