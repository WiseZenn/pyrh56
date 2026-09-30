"""
Frame validation and clamping before sending to hardware.

Rules (aligned with core.py design)
===================================
- Frame must be exactly 6 integer values.
- Every value must be finite (no NaN / Inf).
- Finger servos: 0-1000.
- Thumb flex: default range 0-1000; optional profiles can narrow the range.
- Thumb rotation: safe default 900.
- **Validation failure raises an exception -- never silently send.**
- Connectivity is enforced by the transport layer.
"""

import math
from collections.abc import Sequence

from .configuration import DEFAULT_LIMITS, HandLimits
from .constants import (
    RH56_CLOSE_FRAME,
    RH56_OPEN_FRAME,
    RH56_THUMB_FLEX_CLOSE_LIMIT,
    RH56_THUMB_FLEX_INDEX,
    RH56_THUMB_FLEX_OPEN_LIMIT,
    SERVO_COUNT,
    SERVO_MAX,
    SERVO_MIN,
)
from .exceptions import RH56ServoLimitError, RH56ValidationError


def normalize_u16_vector(
    values: Sequence[int | float],
    *,
    name: str,
    count: int = SERVO_COUNT,
    minimum: int = SERVO_MIN,
    maximum: int = SERVO_MAX,
) -> list[int]:
    """Validate, round, range-check, and return unsigned 16-bit command values."""
    if values is None:
        raise RH56ValidationError(f"{name} must not be None")

    if len(values) != count:
        raise RH56ValidationError(f"{name} must contain {count} values, got {len(values)}")

    result: list[int] = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RH56ValidationError(
                f"{name}[{index}] must be int or float, got {type(value).__name__}"
            )
        if not math.isfinite(value):
            raise RH56ValidationError(f"{name}[{index}] must be finite, got {value}")

        normalized = round(value)
        if not minimum <= normalized <= maximum:
            raise RH56ValidationError(
                f"{name}[{index}] out of range [{minimum}, {maximum}]: {normalized}"
            )
        result.append(normalized)

    return result


def normalize_angle_command(
    frame: Sequence[int | float],
    limits: HandLimits = DEFAULT_LIMITS,
) -> list[int]:
    """Validate, round, and return the only angle form accepted by protocol writes."""
    if frame is None:
        raise RH56ValidationError("frame must not be None")

    if len(frame) != SERVO_COUNT:
        raise RH56ValidationError(
            f"frame must contain exactly {SERVO_COUNT} values, got {len(frame)}"
        )

    result: list[int] = []
    for i, (value, limit) in enumerate(zip(frame, limits.as_tuple())):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RH56ValidationError(
                f"frame[{i}] type error: expected int/float, got {type(value).__name__}"
            )
        if not math.isfinite(value):
            raise RH56ValidationError(f"frame[{i}] is not a finite number: {value}")

        normalized = round(value)
        if normalized < limit.minimum or normalized > limit.maximum:
            raise RH56ServoLimitError(
                f"frame[{i}] out of range [{limit.minimum}, {limit.maximum}]: {normalized}"
            )
        result.append(normalized)

    return result


def validate_frame(frame: Sequence[int | float]) -> None:
    """Strictly validate a 6-servo frame. Raises on any violation.

    Raises
    ------
    RH56ValidationError
        Length, type, or finiteness violation.
    RH56ServoLimitError
        A servo value exceeds hardware limits.
    """
    normalize_angle_command(frame, DEFAULT_LIMITS)


def normalize_angle_targets(
    targets: Sequence[int | float | None],
    limits: HandLimits = DEFAULT_LIMITS,
) -> list[int | None]:
    """Validate feedback-wait targets; None excludes a channel from arrival checks."""
    if targets is None or len(targets) != SERVO_COUNT:
        raise RH56ValidationError("target must contain exactly 6 values")
    result: list[int | None] = []
    for index, (value, limit) in enumerate(zip(targets, limits.as_tuple())):
        if value is None:
            result.append(None)
        else:
            normalized = normalize_u16_vector(
                [value],
                name=f"target[{index}]",
                count=1,
                minimum=limit.minimum,
                maximum=limit.maximum,
            )
            result.append(normalized[0])
    if all(value is None for value in result):
        raise RH56ValidationError("target must select at least one channel")
    return result


def clamp_servo_value(value: float, finger_index: int) -> int:
    """Clamp a single servo value to its safe range (no exception).

    Use this instead of ``validate_frame`` when you need **silent correction**
    rather than hard errors (e.g. building a frame from untrusted external input).
    """
    if finger_index == RH56_THUMB_FLEX_INDEX:
        lo, hi = RH56_THUMB_FLEX_CLOSE_LIMIT, RH56_THUMB_FLEX_OPEN_LIMIT
    else:
        lo, hi = SERVO_MIN, SERVO_MAX
    return max(lo, min(hi, round(value)))


def clamp_frame(frame: list[int]) -> list[int]:
    """Clamp every servo in the frame to safe ranges. Returns a new list."""
    return [clamp_servo_value(v, i) for i, v in enumerate(frame[:SERVO_COUNT])]


def apply_thumb_limit(frame: list[int]) -> list[int]:
    """Ensure thumb flex and rotation respect hard limits.

    Unlike ``clamp_frame``, only the thumb is modified; finger values pass through.
    """
    return normalize_angle_command(frame, DEFAULT_LIMITS)


def make_safe_open_frame(limits: HandLimits = DEFAULT_LIMITS) -> list[int]:
    """Select the open preset within configured ranges, including optional conservative limits."""
    return _preset_within_limits(RH56_OPEN_FRAME, limits)


def make_safe_close_frame(limits: HandLimits = DEFAULT_LIMITS) -> list[int]:
    """Select the close preset within configured ranges."""
    return _preset_within_limits(RH56_CLOSE_FRAME, limits)


def _preset_within_limits(frame: Sequence[int], limits: HandLimits) -> list[int]:
    return [
        max(limit.minimum, min(value, limit.maximum))
        for value, limit in zip(frame, limits.as_tuple())
    ]
