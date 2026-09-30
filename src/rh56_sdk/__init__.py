"""Stable public API for the RH56 low-level hardware SDK."""

from .configuration import (
    CONSERVATIVE_LIMITS,
    DEFAULT_LIMITS,
    FACTORY_LIMITS,
    FaultPolicy,
    HandLimits,
    JointLimit,
    RetryPolicy,
    RH56Config,
)
from .driver import RH56Driver
from .enums import ErrorFlag, Finger, StatusCode
from .exceptions import RH56Error
from .models import FeedbackSnapshot, SerialPortInfo

__version__ = "0.4.0"

__all__ = [
    "CONSERVATIVE_LIMITS",
    "DEFAULT_LIMITS",
    "FACTORY_LIMITS",
    "ErrorFlag",
    "FaultPolicy",
    "FeedbackSnapshot",
    "Finger",
    "HandLimits",
    "JointLimit",
    "RH56Config",
    "RH56Driver",
    "RH56Error",
    "RetryPolicy",
    "SerialPortInfo",
    "StatusCode",
]
