"""Stable public API for the RH56 low-level hardware SDK."""

from .configuration import (
    DEFAULT_LIMITS,
    CONSERVATIVE_LIMITS,
    FACTORY_LIMITS,
    HandLimits,
    JointLimit,
    RH56Config,
    RetryPolicy,
    FaultPolicy,
)
from .driver import RH56Driver
from .enums import ErrorFlag, Finger, StatusCode
from .exceptions import RH56Error
from .models import FeedbackSnapshot, SerialPortInfo

__version__ = "0.4.0"

__all__ = [
    "RH56Driver",
    "RH56Config",
    "RetryPolicy",
    "FaultPolicy",
    "JointLimit",
    "HandLimits",
    "DEFAULT_LIMITS",
    "CONSERVATIVE_LIMITS",
    "FACTORY_LIMITS",
    "Finger",
    "StatusCode",
    "ErrorFlag",
    "FeedbackSnapshot",
    "SerialPortInfo",
    "RH56Error",
]
