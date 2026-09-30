"""High-level RH56 grasp controller built on RH56Driver."""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from rh56_sdk.constants import RH56_OPEN_FRAME

from .benchmark_logger import BenchmarkLogger
from .gestures import MAIN_FINGERS, get_closure_target, get_gesture
from .pressure_close import PressureCloseConfig, PressureCloser, PressureCloseResult
from .state_machine import GraspState, GraspStateMachine


@dataclass
class GraspTrialResult:
    trial_id: int
    grasp_type: str
    pressure_result: PressureCloseResult
    target_frame: list[int]
    speed: int
    force_threshold: int
    object_name: str = ""
    object_size: str = ""
    object_weight: str = ""
    object_material: str = ""


class GraspController:
    """Coordinate pre-shape, pressure closing, holding, release, and logging."""

    def __init__(
        self,
        driver,
        logger: BenchmarkLogger | None = None,
        default_speed: int = 250,
        pre_shape_timeout: float = 3.0,
        pre_shape_tolerance: int = 30,
    ) -> None:
        self.driver = driver
        self.logger = logger
        self.default_speed = default_speed
        self.state_machine = GraspStateMachine()
        self.pressure_closer = PressureCloser(driver)
        self.current_frame = list(RH56_OPEN_FRAME)
        self.pre_shape_timeout = pre_shape_timeout
        self.pre_shape_tolerance = pre_shape_tolerance

    @property
    def state(self) -> GraspState:
        return self.state_machine.state

    def open(self, speed: int | None = None) -> None:
        """Move to full open hand."""
        self._set_speed_if_needed(speed)
        self.driver.move_to(RH56_OPEN_FRAME)
        self.current_frame = list(RH56_OPEN_FRAME)
        if self.state == GraspState.IDLE:
            self.state_machine.transition(GraspState.OPEN)
        else:
            self.state_machine.force(GraspState.OPEN)

    def release(self, speed: int | None = None) -> None:
        """Release object and return to open."""
        if self.state != GraspState.RELEASE:
            self.state_machine.force(GraspState.RELEASE)
        self.open(speed=speed)

    def pre_shape(self, grasp_type: str, speed: int | None = None) -> list[int]:
        """Move to a named pre-shape frame."""
        frame = get_gesture(grasp_type)
        self._set_speed_if_needed(speed)
        self.driver.move_to(frame)
        if grasp_type == "pinch":
            reached = self._wait_finger_angle(
                finger=5,
                target=frame[5],
                tolerance=self.pre_shape_tolerance,
                timeout=self.pre_shape_timeout,
            )
            if not reached:
                self.state_machine.force(GraspState.ERROR)
                raise TimeoutError(
                    f"Thumb rotation did not reach pinch target {frame[5]} "
                    f"within {self.pre_shape_timeout:.1f}s"
                )
        self.current_frame = list(frame)
        if self.state in (GraspState.IDLE, GraspState.OPEN):
            self.state_machine.transition(GraspState.PRE_SHAPE)
        else:
            self.state_machine.force(GraspState.PRE_SHAPE)
        return frame

    def close_until_contact(
        self,
        grasp_type: str,
        force_threshold: int = 80,
        speed: int | None = None,
        active_fingers: Sequence[int] | None = None,
        config: PressureCloseConfig | None = None,
    ) -> PressureCloseResult:
        """Incrementally close from current frame until contact is detected."""
        self._set_speed_if_needed(speed)
        target = get_closure_target(grasp_type)
        active = list(active_fingers or MAIN_FINGERS.get(grasp_type, [0, 1, 2, 3, 4]))
        close_config = config or PressureCloseConfig(force_threshold=force_threshold)
        close_config.force_threshold = force_threshold
        self.state_machine.force(GraspState.CLOSING)
        result = self.pressure_closer.close_until_contact(
            self.current_frame,
            target,
            active,
            close_config,
        )
        self.current_frame = list(result.final_frame)
        if result.success:
            self.state_machine.force(GraspState.HOLD)
        elif result.contact_fingers:
            self.state_machine.force(GraspState.CONTACT_DETECTED)
        else:
            self.state_machine.force(GraspState.ERROR)
        return result

    def grasp(
        self,
        grasp_type: str,
        force_threshold: int = 80,
        speed: int | None = None,
        object_name: str = "",
        object_size: str = "",
        object_weight: str = "",
        object_material: str = "",
        config: PressureCloseConfig | None = None,
    ) -> GraspTrialResult:
        """Run pre-shape -> pressure close and optionally log one trial."""
        trial_id = self.logger.next_trial_id() if self.logger else 1
        target_frame = self.pre_shape(grasp_type, speed=speed)
        result = self.close_until_contact(
            grasp_type,
            force_threshold=force_threshold,
            speed=speed,
            config=config,
        )
        trial = GraspTrialResult(
            trial_id=trial_id,
            grasp_type=grasp_type,
            pressure_result=result,
            target_frame=target_frame,
            speed=speed if speed is not None else self.default_speed,
            force_threshold=force_threshold,
            object_name=object_name,
            object_size=object_size,
            object_weight=object_weight,
            object_material=object_material,
        )
        if self.logger:
            self.logger.log(self._trial_record(trial))
        return trial

    def hold(self, seconds: float) -> None:
        """Remain in HOLD state for *seconds* while checking for reported faults."""
        self.state_machine.force(GraspState.HOLD)
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            status = self.driver.read_status()
            error = self.driver.read_error()
            if any(error) or any(code in {5, 6, 7} for code in status):
                self.state_machine.force(GraspState.ERROR)
                raise RuntimeError(f"RH56 fault during hold: status={status} error={error}")
            time.sleep(0.05)

    def _set_speed_if_needed(self, speed: int | None) -> None:
        value = self.default_speed if speed is None else int(speed)
        self.driver.set_speed([value] * 6)

    def _wait_finger_angle(
        self,
        finger: int,
        target: int,
        tolerance: int,
        timeout: float,
    ) -> bool:
        if timeout <= 0:
            return True
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            angle = self.driver.read_angle()
            if abs(angle[finger] - target) <= tolerance:
                return True
            time.sleep(0.05)
        return False

    @staticmethod
    def _trial_record(trial: GraspTrialResult) -> dict[str, object]:
        result = trial.pressure_result
        return {
            "trial_id": trial.trial_id,
            "timestamp": time.time(),
            "object_name": trial.object_name,
            "object_size": trial.object_size,
            "object_weight": trial.object_weight,
            "object_material": trial.object_material,
            "grasp_type": trial.grasp_type,
            "target_frame": trial.target_frame,
            "speed": trial.speed,
            "force_threshold": trial.force_threshold,
            "actual_position": result.actual_position,
            "force_curve": result.force_curve,
            "max_force": result.max_force,
            "closing_time": result.closing_time,
            "hold_time": result.hold_time,
            "success": result.success,
            "failure_reason": result.failure_reason,
        }
