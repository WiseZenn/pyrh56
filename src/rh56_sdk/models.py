"""Dataclass models shared by the RH56 SDK public API."""

from dataclasses import dataclass
from typing import TypeAlias

JointVector: TypeAlias = tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class SerialPortInfo:
    """Serial adapter information; enumeration does not identify RH56 devices."""

    device: str
    description: str
    hwid: str
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    manufacturer: str | None = None


@dataclass(frozen=True)
class FeedbackSnapshot:
    """Typed snapshot for low-frequency feedback and diagnostics."""

    timestamp: float
    monotonic_time: float
    angle: JointVector | None = None
    force: JointVector | None = None
    status: JointVector | None = None
    error: JointVector | None = None
    current: JointVector | None = None
    temperature: JointVector | None = None
    voltage: int | None = None
