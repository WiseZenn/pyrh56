"""Stable public enums for RH56 hardware channels and status values."""

from enum import IntEnum, IntFlag


class Finger(IntEnum):
    """RH56 six-channel order used by command and feedback vectors."""

    PINKY = 0
    RING = 1
    MIDDLE = 2
    INDEX = 3
    THUMB_FLEX = 4
    THUMB_ROTATION = 5


class StatusCode(IntEnum):
    """Known RH56 per-finger status codes."""

    RELEASING = 0
    GRASPING = 1
    POSITION_REACHED = 2
    FORCE_REACHED = 3
    OVERCURRENT_STOP = 5
    STALL_STOP = 6
    ACTUATOR_FAULT = 7


class ErrorFlag(IntFlag):
    """Known RH56 per-finger error bit flags."""

    NONE = 0
    STALL = 1 << 0
    OVER_TEMPERATURE = 1 << 1
    OVERCURRENT = 1 << 2
    MOTOR_ANOMALY = 1 << 3
    COMMUNICATION = 1 << 4
