"""Diagnostics and characterization helpers kept outside the RH56 driver."""

from __future__ import annotations

import time
from typing import Optional, Protocol, Sequence

from .constants import SERVO_COUNT
from .exceptions import RH56CalibrationError, RH56ValidationError
from .models import FeedbackSnapshot, JointVector

__all__ = ["RH56Diagnostics", "DiagnosticsDriver"]


class DiagnosticsDriver(Protocol):
    @property
    def miss_count(self) -> int: ...

    @property
    def is_stale(self) -> bool: ...

    @property
    def communication_fault(self) -> bool: ...

    @property
    def safe_stop(self) -> bool: ...

    def read_angle(self) -> list[int]: ...

    def read_force(self) -> list[int]: ...

    def read_status(self) -> list[int]: ...

    def read_error(self) -> list[int]: ...

    def read_current(self) -> list[int]: ...

    def read_temperature(self) -> list[int]: ...

    def read_voltage(self) -> int: ...

    def set_speed(self, values: Sequence[int | float]) -> None: ...

    def move_finger(self, finger_index: int, value: int | float) -> None: ...


class RH56Diagnostics:
    """Read-only snapshots and motion characterization for RH56."""

    def __init__(self, hand: DiagnosticsDriver) -> None:
        self._hand = hand

    def read_feedback_snapshot(self) -> FeedbackSnapshot:
        """Read a typed low-frequency feedback snapshot."""
        hand = self._hand
        return FeedbackSnapshot(
            timestamp=time.time(),
            monotonic_time=time.monotonic(),
            angle=_joint_vector(hand.read_angle()),
            force=_joint_vector(hand.read_force()),
            status=_joint_vector(hand.read_status()),
            error=_joint_vector(hand.read_error()),
            current=_joint_vector(hand.read_current()),
            temperature=_joint_vector(hand.read_temperature()),
            voltage=hand.read_voltage(),
        )

    def read_calibration_snapshot(self) -> dict[str, object]:
        """Read angle/force/status/error/current/temp for before/after reports."""
        hand = self._hand
        return {
            "timestamp": time.time(),
            "angle": hand.read_angle(),
            "force": hand.read_force(),
            "status": hand.read_status(),
            "error": hand.read_error(),
            "current": hand.read_current(),
            "temperature": hand.read_temperature(),
            "miss_count": hand.miss_count,
            "is_stale": hand.is_stale,
            "communication_fault": hand.communication_fault,
            "safe_stop": hand.safe_stop,
        }

    def characterize_angle_tracking(
        self,
        *,
        points: Optional[Sequence[int]] = None,
        fingers: Optional[Sequence[int]] = None,
        tolerance: int = 30,
        timeout: float = 2.0,
        dwell: float = 0.05,
        speed: Optional[int] = None,
        require_confirm: bool = True,
    ) -> dict[str, object]:
        """Measure ANGLE_SET -> ANGLE_ACT tracking error."""
        if require_confirm:
            raise RH56CalibrationError(
                "Angle tracking characterization moves the hand. "
                "Call with require_confirm=False after confirming the setup is safe."
            )

        test_points = list(points or (1000, 800, 600, 800, 1000))
        test_fingers = list(fingers or (3,))
        for finger in test_fingers:
            if finger < 0 or finger >= SERVO_COUNT:
                raise RH56ValidationError(f"Finger index out of range: {finger}")
        if speed is not None:
            self._hand.set_speed([int(speed)] * SERVO_COUNT)

        report: dict[str, object] = {
            "timestamp": time.time(),
            "points": test_points,
            "tolerance": tolerance,
            "fingers": {},
        }

        fingers_report = report["fingers"]
        assert isinstance(fingers_report, dict)
        for finger in test_fingers:
            finger_report = []
            for target in test_points:
                self._hand.move_finger(finger, int(target))
                reached, elapsed, actual, status, error = self._wait_angle_reached(
                    finger,
                    int(target),
                    tolerance,
                    timeout,
                    dwell,
                )
                finger_report.append(
                    {
                        "target": int(target),
                        "actual": actual,
                        "error": None if actual is None else actual - int(target),
                        "reached": reached,
                        "time_to_reach": elapsed,
                        "status": status,
                        "hardware_error": error,
                    }
                )
            fingers_report[str(finger)] = finger_report
        return report

    def _wait_angle_reached(
        self,
        finger: int,
        target: int,
        tolerance: int,
        timeout: float,
        dwell: float,
    ) -> tuple[bool, float, int | None, list[int], list[int]]:
        start = time.monotonic()
        last_actual: int | None = None
        last_status: list[int] = []
        last_error: list[int] = []
        while time.monotonic() - start < timeout:
            angle = self._hand.read_angle()
            last_status = self._hand.read_status()
            last_error = self._hand.read_error()
            last_actual = angle[finger]
            if any(last_error) or any(code in {5, 6, 7} for code in last_status):
                return False, time.monotonic() - start, last_actual, last_status, last_error
            if abs(last_actual - target) <= tolerance:
                return True, time.monotonic() - start, last_actual, last_status, last_error
            if dwell > 0:
                time.sleep(dwell)
        return False, time.monotonic() - start, last_actual, last_status, last_error


def _joint_vector(values: Sequence[int]) -> JointVector:
    if len(values) != SERVO_COUNT:
        raise RH56ValidationError(f"expected {SERVO_COUNT} values, got {len(values)}")
    return tuple(int(value) for value in values)  # type: ignore[return-value]
