import unittest

from rh56_grasp import (
    GraspController,
    GraspState,
    PressureCloseConfig,
    get_closure_target,
    get_gesture,
)


class FakeDriver:
    def __init__(self) -> None:
        self.frame = [1000, 1000, 1000, 1000, 1000, 900]
        self.speed = [0] * 6
        self.moves = []
        self.force_zero_offset = [0] * 6

    def set_speed(self, values):
        self.speed = list(values)

    def move_to(self, frame):
        self.frame = list(frame)
        self.moves.append(list(frame))

    def read_angle(self):
        return list(self.frame)

    def read_status(self):
        return [2, 2, 2, 2, 2, 2]

    def read_error(self):
        return [0, 0, 0, 0, 0, 0]

    def read_force(self):
        return self.get_force_net()

    def get_force_net(self):
        force = [0, 0, 0, 0, 0, 0]
        if self.frame[3] <= 175:
            force[3] = 90
        if self.frame[4] <= 225:
            force[4] = 95
        return force


class LaggingNoContactDriver(FakeDriver):
    def __init__(self) -> None:
        super().__init__()
        self.actual = list(self.frame)

    def move_to(self, frame):
        self.frame = list(frame)
        self.actual[5] = frame[5]
        self.moves.append(list(frame))

    def read_angle(self):
        return list(self.actual)

    def get_force_net(self):
        return [0, 0, 0, 0, 0, 0]


class NegativeDriftDriver(FakeDriver):
    def get_force_net(self):
        return [0, 0, 0, -40, -40, 0]


class FingerCollisionDriver(FakeDriver):
    def get_force_net(self):
        force = [0, 0, 0, 0, 0, 0]
        if self.frame[3] <= 20 and self.frame[4] <= 220:
            force[3] = 80
            force[4] = 85
        return force


class CapturingLogger:
    def __init__(self) -> None:
        self.records = []

    def next_trial_id(self) -> int:
        return len(self.records) + 1

    def log(self, record) -> None:
        self.records.append(record)


class GraspControllerTests(unittest.TestCase):
    def test_gesture_and_closure_target_are_distinct_for_pinch(self) -> None:
        self.assertEqual(get_gesture("pinch"), [1000, 1000, 1000, 1000, 1000, 150])
        self.assertEqual(get_closure_target("pinch"), [1000, 1000, 1000, 0, 200, 150])

    def test_pressure_grasp_reaches_hold_and_logs_trial(self) -> None:
        driver = FakeDriver()
        logger = CapturingLogger()
        controller = GraspController(
            driver,
            logger=logger,
            default_speed=200,
        )
        result = controller.grasp(
            "pinch",
            force_threshold=80,
            speed=200,
            object_name="block",
            config=PressureCloseConfig(
                force_threshold=80,
                step=25,
                period=0.0,
                timeout=1.0,
                hold_time=0.0,
            ),
        )

        self.assertTrue(result.pressure_result.success)
        self.assertEqual(controller.state, GraspState.HOLD)
        self.assertEqual(result.pressure_result.contact_fingers, [3, 4])
        self.assertEqual(len(logger.records), 1)
        self.assertEqual(logger.records[0]["object_name"], "block")
        self.assertEqual(logger.records[0]["grasp_type"], "pinch")
        self.assertTrue(logger.records[0]["success"])

    def test_command_target_does_not_end_before_actual_target(self) -> None:
        driver = LaggingNoContactDriver()
        controller = GraspController(driver, logger=CapturingLogger(), default_speed=200)
        result = controller.grasp(
            "pinch",
            force_threshold=80,
            speed=200,
            config=PressureCloseConfig(
                force_threshold=80,
                step=200,
                period=0.0,
                timeout=0.01,
                hold_time=0.0,
                target_tolerance=30,
            ),
        )

        self.assertFalse(result.pressure_result.success)
        self.assertEqual(result.pressure_result.failure_reason, "timeout")
        self.assertGreater(result.pressure_result.actual_position[3], 30)

    def test_default_contact_detection_ignores_negative_force_drift(self) -> None:
        driver = NegativeDriftDriver()
        controller = GraspController(driver, logger=CapturingLogger(), default_speed=200)
        result = controller.grasp(
            "pinch",
            force_threshold=30,
            speed=200,
            config=PressureCloseConfig(
                force_threshold=30,
                step=200,
                period=0.0,
                timeout=0.01,
                hold_time=0.0,
            ),
        )

        self.assertFalse(result.pressure_result.success)
        self.assertEqual(result.pressure_result.contact_fingers, [])

    def test_pinch_pre_shape_rotates_thumb_before_closing(self) -> None:
        driver = FakeDriver()
        controller = GraspController(driver, logger=CapturingLogger(), default_speed=200)

        controller.pre_shape("pinch", speed=200)

        self.assertEqual(driver.moves[0], [1000, 1000, 1000, 1000, 1000, 150])

    def test_pinch_finger_collision_near_target_is_not_success(self) -> None:
        driver = FingerCollisionDriver()
        controller = GraspController(driver, logger=CapturingLogger(), default_speed=200)

        result = controller.grasp(
            "pinch",
            force_threshold=50,
            speed=200,
            config=PressureCloseConfig(
                force_threshold=50,
                step=200,
                period=0.0,
                timeout=1.0,
                hold_time=0.0,
                collision_target_tolerance=80,
            ),
        )

        self.assertFalse(result.pressure_result.success)
        self.assertTrue(result.pressure_result.possible_finger_collision)
        self.assertEqual(result.pressure_result.failure_reason, "finger_collision_or_no_object")


if __name__ == "__main__":
    unittest.main()
