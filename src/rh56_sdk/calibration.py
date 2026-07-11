"""Calibration helpers kept outside the low-level RH56 driver."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any, Protocol

from .constants import SERVO_COUNT
from .exceptions import RH56BusyError, RH56CalibrationError, RH56ValidationError
from .registers import REG_GESTURE_FORCE_CLB

__all__ = ["ForceCalibration", "ForceCalibrationProfile", "CalibrationDriver"]


class CalibrationDriver(Protocol):
    is_calibrating: bool
    _calibration_busy_until: float | None
    last_calibration_time: float | None
    last_feedback: dict[str, object]
    force_zero_offset: list[int]

    def _ensure_connected(self) -> None: ...

    def _write_u8(self, addr: int, value: int, wait_ack: bool = True) -> None: ...

    def read_error(self) -> list[int]: ...

    def read_force(self) -> list[int]: ...

    def read_status(self) -> list[int]: ...


class ForceCalibration:
    """Force calibration and software baseline routines for RH56."""

    def __init__(self, hand: CalibrationDriver) -> None:
        self._hand = hand

    def run_official(
        self,
        *,
        wait: bool = True,
        timeout: float = 8.0,
        require_confirm: bool = True,
    ) -> bool:
        """Trigger the official RH56 force-sensor calibration routine."""
        hand = self._hand
        hand._ensure_connected()
        if require_confirm:
            raise RH56CalibrationError(
                "Official force calibration moves the hand automatically. "
                "Ensure the hand is unloaded and call with require_confirm=False."
            )
        if hand.is_calibrating:
            raise RH56BusyError("RH56 is already calibrating")

        errors_before = hand.read_error()
        if any(errors_before):
            raise RH56CalibrationError(
                f"Cannot calibrate while error exists: {errors_before}"
            )

        started = False
        hand.is_calibrating = True
        hand._calibration_busy_until = time.monotonic() + float(timeout)
        try:
            hand._write_u8(REG_GESTURE_FORCE_CLB, 1, wait_ack=True)
            started = True
            if not wait:
                hand.last_calibration_time = time.time()
                return True

            time.sleep(float(timeout))

            errors_after = hand.read_error()
            force_after = hand.read_force()
            status_after = hand.read_status()
            if any(errors_after):
                raise RH56CalibrationError(
                    f"Calibration finished with errors: {errors_after}"
                )

            hand.last_calibration_time = time.time()
            hand.last_feedback["force_after_calibration"] = force_after
            hand.last_feedback["status_after_calibration"] = status_after
            return True
        finally:
            if wait or not started:
                hand.is_calibrating = False
                hand._calibration_busy_until = None

    def measure_baseline(self, *, samples: int = 50, interval: float = 0.02) -> list[int]:
        """Record software-side unloaded FORCE_ACT baseline."""
        force_samples = self._sample_force(samples, interval)
        channels = list(zip(*force_samples))
        offset = [int(round(statistics.median(ch))) for ch in channels]
        self._hand.force_zero_offset = offset
        self._hand.last_calibration_time = time.time()
        return list(offset)

    def validate_baseline(
        self,
        *,
        samples: int = 20,
        tolerance: int = 30,
        interval: float = 0.02,
    ) -> dict[str, object]:
        """Sample FORCE_ACT and judge whether unloaded force is near zero."""
        force_samples = self._sample_force(samples, interval)
        channels = list(zip(*force_samples))
        median = [int(round(statistics.median(ch))) for ch in channels]
        maximum_abs = [max(abs(v) for v in ch) for ch in channels]
        std = [statistics.pstdev(ch) if len(ch) > 1 else 0.0 for ch in channels]
        ok = all(abs(v) <= tolerance for v in median)
        return {
            "ok": ok,
            "samples": len(force_samples),
            "tolerance": tolerance,
            "median": median,
            "max_abs": maximum_abs,
            "std": std,
            "force_zero_offset": list(self._hand.force_zero_offset),
        }

    def get_net_force(self) -> list[int]:
        """Return force with the software zero offset removed."""
        raw = self._hand.read_force()
        return [int(r - z) for r, z in zip(raw, self._hand.force_zero_offset)]

    def save_profile(self, path: str | Path, profile: dict[str, Any] | None = None) -> None:
        """Save the current or supplied force baseline profile as JSON."""
        payload = profile or {
            "timestamp": time.time(),
            "force_zero_offset": list(self._hand.force_zero_offset),
        }
        Path(path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_profile(self, path: str | Path) -> dict[str, Any]:
        """Load a baseline profile and apply its `force_zero_offset`."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        offset = payload.get("force_zero_offset")
        if not isinstance(offset, list) or len(offset) != SERVO_COUNT:
            raise RH56ValidationError("force_zero_offset must contain 6 values")
        self._hand.force_zero_offset = [int(value) for value in offset]
        return payload

    def _sample_force(self, samples: int, interval: float) -> list[list[int]]:
        if samples < 1:
            raise RH56ValidationError("samples must be >= 1")
        collected = []
        for index in range(samples):
            collected.append(self._hand.read_force())
            if index < samples - 1 and interval > 0:
                time.sleep(interval)
        return collected


# Backward-compatible alias matching the planning document terminology.
ForceCalibrationProfile = dict[str, Any]
