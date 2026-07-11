"""Force-aware incremental closing for RH56 grasps."""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence



FAULT_STATUS = {5, 6, 7}


@dataclass
class PressureCloseConfig:
    force_threshold: int = 80
    step: int = 25
    period: float = 0.05
    timeout: float = 5.0
    hold_time: float = 1.0
    slip_drop: int = 40
    min_angle: int = 0
    thumb_min_angle: int = 200
    target_tolerance: int = 30
    contact_direction: str = "positive"
    collision_target_tolerance: int = 80


@dataclass
class PressureCloseResult:
    success: bool
    final_frame: List[int]
    actual_position: List[int]
    force_curve: List[List[int]]
    max_force: int
    closing_time: float
    hold_time: float
    contact_fingers: List[int]
    slip_detected: bool = False
    possible_finger_collision: bool = False
    failure_reason: str = ""
    status: List[int] = field(default_factory=list)
    error: List[int] = field(default_factory=list)


class PressureCloser:
    """Close selected fingers until net force crosses a threshold."""

    def __init__(self, driver) -> None:
        self.driver = driver

    def close_until_contact(
        self,
        start_frame: Sequence[int],
        target_frame: Sequence[int],
        active_fingers: Sequence[int],
        config: Optional[PressureCloseConfig] = None,
    ) -> PressureCloseResult:
        config = config or PressureCloseConfig()
        frame = list(start_frame)
        target = list(target_frame)
        active = list(active_fingers)
        frozen: Dict[int, bool] = {finger: False for finger in active}
        force_curve: List[List[int]] = []
        start = time.monotonic()
        last_angle = list(frame)
        last_status: List[int] = []
        last_error: List[int] = []
        max_force = 0
        command_target_reached = False

        while time.monotonic() - start < config.timeout:
            force = self._read_force_net()
            status = self.driver.read_status()
            error = self.driver.read_error()
            angle = self.driver.read_angle()
            last_angle = angle
            last_status = status
            last_error = error
            force_curve.append(force)
            max_force = max(max_force, max(abs(v) for v in force))

            if any(error):
                return self._result(False, frame, angle, force_curve, max_force, start,
                                    0.0, frozen, "hardware_error", status, error)
            if any(code in FAULT_STATUS for code in status):
                return self._result(False, frame, angle, force_curve, max_force, start,
                                    0.0, frozen, "fault_status", status, error)

            contact_changed = False
            for finger in active:
                if self._contact_detected(force[finger], config):
                    if not frozen[finger]:
                        frame[finger] = self._safe_freeze_target(finger, angle[finger], config)
                        frozen[finger] = True
                        contact_changed = True

            if contact_changed:
                self.driver.move_to(frame)

            for finger in active:
                if self._contact_detected(force[finger], config):
                    frozen[finger] = True

            if all(frozen.values()):
                possible_collision = self._actual_target_reached(
                    angle,
                    target,
                    active,
                    config.collision_target_tolerance,
                )
                hold = self._hold(config, force_curve, max_force)
                return self._result(
                    not hold["slip_detected"] and not possible_collision,
                    frame,
                    self.driver.read_angle(),
                    force_curve,
                    hold["max_force"],
                    start,
                    hold["hold_time"],
                    frozen,
                    self._contact_failure_reason(hold["slip_detected"], possible_collision),
                    self.driver.read_status(),
                    self.driver.read_error(),
                    slip_detected=hold["slip_detected"],
                    possible_finger_collision=possible_collision,
                )

            moved = False
            if not command_target_reached:
                for finger in active:
                    if frozen[finger]:
                        continue
                    next_value = max(target[finger], frame[finger] - config.step)
                    if finger == 4:
                        next_value = max(config.thumb_min_angle, next_value)
                    else:
                        next_value = max(config.min_angle, next_value)
                    if next_value != frame[finger]:
                        frame[finger] = next_value
                        moved = True

                if moved:
                    self.driver.move_to(frame)
                else:
                    command_target_reached = True

            if command_target_reached and self._actual_target_reached(
                angle, target, active, config.target_tolerance
            ):
                reason = "actual_target_reached_without_contact"
                return self._result(False, frame, angle, force_curve, max_force, start,
                                    0.0, frozen, reason, status, error)

            if config.period > 0:
                time.sleep(config.period)

        return self._result(False, frame, last_angle, force_curve, max_force, start,
                            0.0, frozen, "timeout", last_status, last_error)

    def _read_force_net(self) -> List[int]:
        if hasattr(self.driver, "get_force_net"):
            return list(self.driver.get_force_net())
        return list(self.driver.read_force())

    def _hold(
        self,
        config: PressureCloseConfig,
        force_curve: List[List[int]],
        max_force: int,
    ) -> Dict[str, object]:
        start = time.monotonic()
        slip_detected = False
        baseline = max_force
        while time.monotonic() - start < config.hold_time:
            force = self._read_force_net()
            force_curve.append(force)
            current = max(abs(v) for v in force)
            max_force = max(max_force, current)
            if baseline - current >= config.slip_drop:
                slip_detected = True
                break
            if config.period > 0:
                time.sleep(config.period)
        return {
            "hold_time": time.monotonic() - start,
            "max_force": max_force,
            "slip_detected": slip_detected,
        }

    @staticmethod
    def _actual_target_reached(
        angle: List[int],
        target: List[int],
        active: List[int],
        tolerance: int,
    ) -> bool:
        return all(abs(angle[finger] - target[finger]) <= tolerance for finger in active)

    @staticmethod
    def _contact_detected(force_value: int, config: PressureCloseConfig) -> bool:
        if config.contact_direction == "positive":
            return force_value >= config.force_threshold
        if config.contact_direction == "negative":
            return force_value <= -config.force_threshold
        if config.contact_direction == "absolute":
            return abs(force_value) >= config.force_threshold
        raise ValueError(f"Unknown contact_direction: {config.contact_direction}")

    @staticmethod
    def _safe_freeze_target(
        finger: int,
        actual_angle: int,
        config: PressureCloseConfig,
    ) -> int:
        if finger == 4:
            return max(config.thumb_min_angle, int(actual_angle))
        return max(config.min_angle, int(actual_angle))

    @staticmethod
    def _contact_failure_reason(
        slip_detected: bool,
        possible_finger_collision: bool,
    ) -> str:
        if slip_detected:
            return "slip_detected"
        if possible_finger_collision:
            return "finger_collision_or_no_object"
        return ""

    @staticmethod
    def _result(
        success: bool,
        frame: List[int],
        angle: List[int],
        force_curve: List[List[int]],
        max_force: int,
        start: float,
        hold_time: float,
        frozen: Dict[int, bool],
        failure_reason: str,
        status: List[int],
        error: List[int],
        slip_detected: bool = False,
        possible_finger_collision: bool = False,
    ) -> PressureCloseResult:
        return PressureCloseResult(
            success=success,
            final_frame=list(frame),
            actual_position=list(angle),
            force_curve=[list(sample) for sample in force_curve],
            max_force=max_force,
            closing_time=time.monotonic() - start,
            hold_time=hold_time,
            contact_fingers=[finger for finger, contacted in frozen.items() if contacted],
            slip_detected=slip_detected,
            possible_finger_collision=possible_finger_collision,
            failure_reason=failure_reason,
            status=list(status),
            error=list(error),
        )
