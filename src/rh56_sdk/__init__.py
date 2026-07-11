"""Stable public API for the RH56 low-level hardware SDK."""

from .configuration import (
    CONSERVATIVE_LIMITS,
    FACTORY_LIMITS,
    HandLimits,
    JointLimit,
    RH56Config,
)
from .driver import RH56Driver
from .enums import ErrorFlag, Finger, StatusCode
from .exceptions import RH56Error
from .models import FeedbackSnapshot

__version__ = "0.3.0"

__all__ = [
    "RH56Driver",
    "RH56Config",
    "JointLimit",
    "HandLimits",
    "CONSERVATIVE_LIMITS",
    "FACTORY_LIMITS",
    "Finger",
    "StatusCode",
    "ErrorFlag",
    "FeedbackSnapshot",
    "RH56Error",
]
