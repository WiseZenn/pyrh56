"""
RH56 driver exception hierarchy.

Each exception class clearly describes the error cause. Callers can
catch by type or catch the common base ``RH56Error``.
"""


class RH56Error(Exception):
    """Base class for all RH56-related exceptions."""


# --- Connection exceptions ---

class RH56ConnectionError(RH56Error):
    """Failed to establish or maintain a serial connection."""


class RH56NotConnectedError(RH56ConnectionError):
    """Attempted communication while not connected."""


# --- Protocol exceptions ---

class RH56ProtocolError(RH56Error):
    """Protocol-level error: frame parse failure, checksum mismatch, etc."""


class RH56ChecksumError(RH56ProtocolError):
    """Received frame checksum does not match."""


class RH56FrameError(RH56ProtocolError):
    """Frame format error (too short, invalid header bytes, etc.)."""


# --- Safety / validation exceptions ---

class RH56SafetyError(RH56Error):
    """Frame validation failed -- sending is blocked to prevent hardware damage."""


class RH56BusyError(RH56SafetyError):
    """Command rejected because the device is busy with an exclusive operation."""


class RH56ValidationError(RH56SafetyError):
    """Input parameter is invalid (value range, type, dimensions, etc.)."""


class RH56ServoLimitError(RH56ValidationError):
    """Servo target value exceeds physical limit."""


# --- Timeout exceptions ---

class RH56TimeoutError(RH56Error):
    """Read operation timed out without receiving a complete response."""


# --- Hardware exceptions ---

class RH56HardwareError(RH56Error):
    """Hardware-reported fault (details available via status register)."""


class RH56CalibrationError(RH56HardwareError):
    """Calibration could not start or did not pass post-calibration validation."""
