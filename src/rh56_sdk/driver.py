"""
RH56 dexterous hand driver -- the single entry point for users.

Usage
=====
.. code-block:: python

    from rh56_sdk import RH56Driver

    hand = RH56Driver("COM3")
    hand.connect()
    hand.open()                     # open hand
    hand.move_finger(0, 500)       # index finger half-close
    hand.close()                    # grasp
    hand.disconnect()

Read timeout & retry
====================
- Read: 100 ms timeout, up to 2 extra retries (3 attempts total), 10 ms interval.
- Write: optional 100 ms ACK wait (disabled in mock mode).
- High-frequency control loops: do not block on retries too long.
  On read failure, keep the last known frame and increment the miss counter.
"""

import logging
import time
import warnings
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

from .constants import (
    RH56_OPEN_FRAME,
    RH56_CLOSE_FRAME,
    SERVO_COUNT,
)
from .configuration import RH56Config
from .enums import Finger
from .registers import (
    REG_ANGLE_SET,
    REG_FORCE_SET,
    REG_SPEED_SET,
    REG_VOLTAGE,
    REG_ANGLE_ACT,
    REG_POS_ACT,
    REG_FORCE_ACT,
    REG_CURRENT,
    REG_ERROR,
    REG_STATUS,
    REG_TEMP,
    REG_SAVE,
    REG_CLEAR_ERROR,
    STATUS_TEXT,
    ERROR_BITS,
)
from .protocol import (
    RH56Protocol,
    build_write_bytes_frame,
    build_reg16_frame,
    build_read_reg16,
    parse_read_response,
    parse_i16_le,
    parse_u16_le,
    parse_u8,
)
from .safety import normalize_angle_command, normalize_u16_vector
from .transport import SerialTransport
from .exceptions import (
    RH56BusyError,
    RH56Error,
    RH56NotConnectedError,
    RH56ProtocolError,
    RH56HardwareError,
    RH56TimeoutError,
    RH56ValidationError,
)

logger = logging.getLogger(__name__)

class TransportProtocol(Protocol):
    _port: str

    @property
    def is_connected(self) -> bool: ...

    @property
    def is_mock(self) -> bool: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def request(self, frame: bytes, timeout: float | None = None) -> bytes: ...

    def write(self, data: bytes) -> None: ...


class RH56Driver:
    """RH56 6-DOF dexterous hand serial bus driver.

    Parameters
    ----------
    port : str
        Serial port name, e.g. ``"COM3"``. Use ``"COM_MOCK"`` for testing.
    baud : int
        Baud rate (default 115200).
    node_id : int
        Bus node ID (default 1).
    timeout : float
        Serial read/write timeout in seconds (default 0.1).
    """

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------
    def __init__(
        self,
        port: str | RH56Config,
        baud: int | None = None,
        node_id: int | None = None,
        timeout: float | None = None,
        transport: TransportProtocol | None = None,
    ) -> None:
        if isinstance(port, RH56Config):
            self._config = port
        else:
            self._config = RH56Config(
                port=port,
                baud=115200 if baud is None else int(baud),
                node_id=1 if node_id is None else int(node_id),
                timeout=0.1 if timeout is None else float(timeout),
            )

        self._node_id = int(self._config.node_id)
        self._transport = transport or SerialTransport(
            self._config.port,
            baud=self._config.baud,
            timeout=self._config.timeout,
        )

        # Track last-set target frame for incremental move_finger
        self._last_commanded_angle: List[int] = list(RH56_OPEN_FRAME)
        self._last_actual_angle: Optional[List[int]] = None
        self._current_frame: List[int] = self._last_commanded_angle

        # Read fault-tolerance state
        self._miss_count: int = 0
        self._max_miss_before_stale: int = self._config.fault.stale_after
        self._max_miss_before_fault: int = self._config.fault.fault_after
        self._communication_fault: bool = False
        self._safe_stop: bool = False

        # Runtime diagnostics state for closed-loop tests and CLI panels.
        self.last_command: Optional[Dict[str, object]] = None
        self.last_feedback: Dict[str, object] = {}
        self.last_read_time: Optional[float] = None
        self.last_error: Optional[str] = None

        # Calibration state. Official force calibration is exclusive because
        # the hand moves automatically for about six seconds.
        self.is_calibrating: bool = False
        self._calibration_busy_until: Optional[float] = None
        self.last_calibration_time: Optional[float] = None
        self.force_zero_offset: List[int] = [0] * SERVO_COUNT

    @classmethod
    def mock(cls) -> "RH56Driver":
        """Create a driver backed by the built-in mock transport."""
        return cls("COM_MOCK")

    # ------------------------------------------------------------------
    #  Connection management
    # ------------------------------------------------------------------
    def connect(self, *, verify: bool = True) -> None:
        """Open the serial connection and optionally sync command state from ANGLE_ACT."""
        self._transport.connect()
        if verify:
            try:
                self.synchronize_command_state()
            except Exception:
                self._transport.disconnect()
                raise

    def disconnect(self) -> None:
        """Close the serial connection."""
        self._transport.disconnect()

    @property
    def is_connected(self) -> bool:
        """Whether the serial port is currently connected."""
        return self._transport.is_connected

    # ==================================================================
    #  Full-frame control
    # ==================================================================
    def move_to(self, frame: Sequence[int | float]) -> None:
        """Send 6 target positions (ANGLE_SET) to all servos.

        Pipeline
        --------
        1. Strict validation (``validate_frame``).
        2. Apply thumb hard limits.
        3. Build batch-write frame -> serial send.
        4. Wait for write ACK (9-byte confirmation).
        5. Cache as current frame.

        Raises
        ------
        RH56ValidationError
            Frame is invalid.
        RH56NotConnectedError
            Serial port not connected.
        """
        if self._communication_fault:
            raise RH56Error(
                "Communication fault: feedback is stale. Restore reads and call "
                "reset_miss_count() before sending motion commands."
            )
        self._refresh_calibration_state()
        if self.is_calibrating:
            raise RH56BusyError(
                "RH56 is calibrating; motion command rejected."
            )
        if self._safe_stop:
            raise RH56Error(
                "Safe stop is active because hardware status reported a fault. "
                "Check status/error and clear the fault before moving."
            )
        normalized = normalize_angle_command(frame, self._config.limits)
        self._write_reg16(REG_ANGLE_SET, normalized, wait_ack=True)
        self._last_commanded_angle = list(normalized)
        self._current_frame = self._last_commanded_angle

    def open(self) -> None:
        """Open hand to the safe open position."""
        self.open_hand()

    def open_hand(self) -> None:
        """Normal validated open command using configured safety limits."""
        self.move_to(RH56_OPEN_FRAME)

    def close(self) -> None:
        """Close hand to the preset grasp position."""
        self.move_to(RH56_CLOSE_FRAME)

    # ==================================================================
    #  Single-finger control
    # ==================================================================
    def move_finger(
        self,
        finger_index: Finger | int,
        value: int | float,
        *,
        base: str = "last_command",
    ) -> None:
        """Move a single finger and send the full frame.

        Parameters
        ----------
        finger_index : int
            0=Pinky, 1=Ring, 2=Middle, 3=Index, 4=Thumb Flex, 5=Thumb Rot.
        value : int
            Target position (0-1000; thumb flex minimum 200).
        """
        finger = int(finger_index)
        if finger < 0 or finger >= SERVO_COUNT:
            raise RH56ValidationError(
                f"Finger index out of range: {finger}, "
                f"valid range [0, {SERVO_COUNT - 1}]"
            )
        if base == "last_command":
            frame = list(self._last_commanded_angle)
        elif base == "actual":
            actual = self.read_angle()
            frame = list(actual)
        else:
            raise RH56ValidationError("base must be 'last_command' or 'actual'")
        frame[finger] = int(value)
        self.move_to(frame)

    # ==================================================================
    #  Servo parameter configuration
    # ==================================================================
    def set_speed(self, values: Sequence[int | float]) -> None:
        """Set servo speeds (SPEED_SET, 6 x 16-bit)."""
        normalized = normalize_u16_vector(values, name="speed", minimum=0, maximum=1000)
        self._write_reg16(REG_SPEED_SET, normalized)

    def set_force_threshold(self, values: Sequence[int | float]) -> None:
        """Set force control thresholds (FORCE_SET, 6 x 16-bit)."""
        normalized = normalize_u16_vector(
            values,
            name="force_threshold",
            minimum=0,
            maximum=1000,
        )
        self._write_reg16(REG_FORCE_SET, normalized)

    # ==================================================================
    #  Angle feedback (recommended: same coordinate space as move_to)
    # ==================================================================
    def read_angle(self) -> List[int]:
        """Read actual angle ANGLE_ACT (6 short, range 0-1000).

        This is the preferred feedback for closed-loop control because
        it shares the same coordinate space as ``move_to()``.
        """
        data = self._read_reg16(REG_ANGLE_ACT, count=6)
        values = parse_u16_le(data, count=6)
        self._record_feedback("angle", values)
        self._last_actual_angle = list(values)
        return values

    # ==================================================================
    #  Actuator position feedback
    # ==================================================================
    def read_actuator_position(self) -> List[int]:
        """Read actuator actual position POS_ACT (6 short, range 0-2000)."""
        data = self._read_reg16(REG_POS_ACT, count=6)
        values = parse_u16_le(data, count=6)
        self._record_feedback("actuator_position", values)
        return values

    # Deprecated -- kept for backward compatibility
    def read_position(self) -> List[int]:
        """Deprecated: use ``read_angle()`` or ``read_actuator_position()``.

        Defaults to ANGLE_ACT (0-1000).
        """
        warnings.warn(
            "read_position() is deprecated. Use read_angle() or "
            "read_actuator_position() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.read_angle()

    # ==================================================================
    #  Force / current / voltage feedback
    # ==================================================================
    def read_force(self) -> List[int]:
        """Read actual force FORCE_ACT (6 signed shorts).

        Small negative values like -1, -5 may appear when unloaded;
        the device uses 16-bit two's complement encoding.
        """
        data = self._read_reg16(REG_FORCE_ACT, count=6)
        values = parse_i16_le(data, count=6)
        self._record_feedback("force", values)
        return values

    def read_current(self) -> List[int]:
        """Read current CURRENT (6 short, unit mA)."""
        data = self._read_reg16(REG_CURRENT, count=6)
        values = parse_u16_le(data, count=6)
        self._record_feedback("current", values)
        return values

    def read_voltage(self) -> int:
        """Read voltage VOLTAGE (1 short)."""
        data = self._read_reg16(REG_VOLTAGE, count=1)
        value = parse_u16_le(data, count=1)[0]
        self._record_feedback("voltage", value)
        return value

    # ==================================================================
    #  Status / error / temperature feedback (byte arrays)
    # ==================================================================
    def read_status(self) -> List[int]:
        """Read status codes STATUS (6 bytes).

        Per-finger meaning: see ``STATUS_TEXT``.
        """
        data = self._read_bytes(REG_STATUS, length=6)
        values = parse_u8(data, count=6)
        self._record_feedback("status", values)
        self._update_safe_stop_from_status(values)
        return values

    def read_error(self) -> List[int]:
        """Read error codes ERROR (6 bytes).

        Per-finger bit meanings: see ``ERROR_BITS``.
        """
        data = self._read_bytes(REG_ERROR, length=6)
        values = parse_u8(data, count=6)
        self._record_feedback("error", values)
        if any(values):
            self._safe_stop = True
            self.last_error = f"Hardware error bits reported: {values}"
        return values

    def read_temperature(self) -> List[int]:
        """Read temperature TEMP (6 bytes, unit degC)."""
        data = self._read_bytes(REG_TEMP, length=6)
        values = parse_u8(data, count=6)
        self._record_feedback("temperature", values)
        return values

    # ==================================================================
    #  Composite feedback
    # ==================================================================
    def read_feedback(self) -> Dict[str, List[int]]:
        """Read all feedback registers at once.

        Note: this issues 7 independent read requests. Suitable for
        low-frequency diagnostics; for high-frequency control loops,
        read ``read_angle()`` + ``read_force()`` + ``read_status()`` individually.
        """
        return {
            "angle": self.read_angle(),
            "actuator_position": self.read_actuator_position(),
            "force": self.read_force(),
            "current": self.read_current(),
            "status": self.read_status(),
            "error": self.read_error(),
            "temperature": self.read_temperature(),
        }

    # ==================================================================
    #  Status / error decoding helpers
    # ==================================================================
    @staticmethod
    def decode_status(status_byte: int) -> Tuple[int, str]:
        """Decode a single-finger status byte to (code, description)."""
        text = STATUS_TEXT.get(status_byte, f"Unknown status ({status_byte})")
        return status_byte, text

    @staticmethod
    def decode_error(error_byte: int) -> List[str]:
        """Decode a single-finger error byte to a list of fault names."""
        return [
            name
            for bit, name in ERROR_BITS.items()
            if error_byte & (1 << bit)
        ]

    @staticmethod
    def has_error(error_byte: int) -> bool:
        """Check whether an error byte has any fault flags set."""
        return error_byte != 0

    # ==================================================================
    #  System commands (use with care)
    # ==================================================================
    def clear_error(self, *, verify: bool = True, settle_time: float = 0.05) -> None:
        """Clear error state and verify hardware fault registers by default."""
        self._write_u8(REG_CLEAR_ERROR, 1, wait_ack=True)
        if not verify:
            return

        if settle_time > 0:
            time.sleep(settle_time)

        errors = self.read_error()
        status = self.read_status()
        if any(errors) or any(code in {5, 6, 7} for code in status):
            self._safe_stop = True
            self.last_error = (
                f"Hardware fault remains after clear_error: "
                f"errors={errors}, status={status}"
            )
            raise RH56HardwareError(self.last_error)

        self._safe_stop = False
        self.last_error = None

    def save_parameters(self) -> None:
        """Save current parameters to Flash (SAVE = 1).

        .. warning::
           SAVE is a special command. The hand first replies with a write ACK,
           then sends a save-result frame ~1 second later. This method does
           not wait for the result frame; callers should verify separately.
        """
        logger.info("Sending SAVE command -- verify result after ~1 second")
        self._write_u8(REG_SAVE, 1, wait_ack=False)

    # ==================================================================
    #  Calibration / characterization
    # ==================================================================
    def calibrate_force_sensor(
        self,
        wait: bool = True,
        timeout: float = 8.0,
        require_confirm: bool = True,
    ) -> bool:
        """Deprecated: use ``ForceCalibration(hand).run_official(...)``."""
        warnings.warn(
            "calibrate_force_sensor() moved to ForceCalibration.run_official().",
            DeprecationWarning,
            stacklevel=2,
        )
        from .calibration import ForceCalibration

        return ForceCalibration(self).run_official(
            wait=wait,
            timeout=timeout,
            require_confirm=require_confirm,
        )

    def read_calibration_snapshot(self) -> Dict[str, object]:
        """Deprecated: use ``RH56Diagnostics(hand).read_calibration_snapshot()``."""
        warnings.warn(
            "read_calibration_snapshot() moved to RH56Diagnostics.",
            DeprecationWarning,
            stacklevel=2,
        )
        from .diagnostics import RH56Diagnostics

        return RH56Diagnostics(self).read_calibration_snapshot()

    def validate_force_zero(
        self,
        samples: int = 20,
        tolerance: int = 30,
        interval: float = 0.02,
    ) -> Dict[str, object]:
        """Deprecated: use ``ForceCalibration(hand).validate_baseline(...)``."""
        warnings.warn(
            "validate_force_zero() moved to ForceCalibration.validate_baseline().",
            DeprecationWarning,
            stacklevel=2,
        )
        from .calibration import ForceCalibration

        return ForceCalibration(self).validate_baseline(
            samples=samples,
            tolerance=tolerance,
            interval=interval,
        )

    def calibrate_force_zero_offset(
        self,
        samples: int = 50,
        interval: float = 0.02,
    ) -> List[int]:
        """Deprecated: use ``ForceCalibration(hand).measure_baseline(...)``."""
        warnings.warn(
            "calibrate_force_zero_offset() moved to ForceCalibration.measure_baseline().",
            DeprecationWarning,
            stacklevel=2,
        )
        from .calibration import ForceCalibration

        return ForceCalibration(self).measure_baseline(
            samples=samples,
            interval=interval,
        )

    def get_force_net(self) -> List[int]:
        """Deprecated: use ``ForceCalibration(hand).get_net_force()``."""
        warnings.warn(
            "get_force_net() moved to ForceCalibration.get_net_force().",
            DeprecationWarning,
            stacklevel=2,
        )
        from .calibration import ForceCalibration

        return ForceCalibration(self).get_net_force()

    def characterize_angle_tracking(
        self,
        points: Optional[Sequence[int]] = None,
        fingers: Optional[Sequence[int]] = None,
        tolerance: int = 30,
        timeout: float = 2.0,
        dwell: float = 0.05,
        speed: Optional[int] = None,
        require_confirm: bool = True,
    ) -> Dict[str, object]:
        """Deprecated: use ``RH56Diagnostics(hand).characterize_angle_tracking()``."""
        warnings.warn(
            "characterize_angle_tracking() moved to RH56Diagnostics.",
            DeprecationWarning,
            stacklevel=2,
        )
        from .diagnostics import RH56Diagnostics

        return RH56Diagnostics(self).characterize_angle_tracking(
            points=points,
            fingers=fingers,
            tolerance=tolerance,
            timeout=timeout,
            dwell=dwell,
            speed=speed,
            require_confirm=require_confirm,
        )

    # ==================================================================
    #  Emergency operations
    # ==================================================================
    def stop_motion(self) -> None:
        """Set SPEED_SET to zero and verify ACK."""
        self.set_speed([0] * SERVO_COUNT)

    def stop(self) -> None:
        """Deprecated: use stop_motion()."""
        warnings.warn(
            "stop() is deprecated; use stop_motion().",
            DeprecationWarning,
            stacklevel=2,
        )
        self.stop_motion()

    def recover_open_unchecked(self, *, confirm: bool = False) -> None:
        """Low-level recovery command; bypasses validation and ACK only when confirmed."""
        if not confirm:
            raise RH56ValidationError(
                "recover_open_unchecked() bypasses validation; pass confirm=True"
            )
        logger.warning("Sending unchecked recovery open command")
        self._transport.write(
            build_reg16_frame(self._node_id, REG_ANGLE_SET, RH56_OPEN_FRAME)
        )
        self._last_commanded_angle = list(RH56_OPEN_FRAME)
        self._current_frame = self._last_commanded_angle

    def emergency_open(self) -> None:
        """Deprecated: use recover_open_unchecked(confirm=True)."""
        warnings.warn(
            "emergency_open() is deprecated; use recover_open_unchecked(confirm=True).",
            DeprecationWarning,
            stacklevel=2,
        )
        self.recover_open_unchecked(confirm=True)

    # ==================================================================
    #  Fault-tolerance state
    # ==================================================================
    @property
    def miss_count(self) -> int:
        """Consecutive read failure count."""
        return self._miss_count

    @property
    def is_stale(self) -> bool:
        """Whether reads have failed too many times consecutively (data may be stale)."""
        return self._miss_count >= self._max_miss_before_stale

    def reset_miss_count(self) -> None:
        """Reset the read failure counter."""
        self._miss_count = 0
        self._communication_fault = False

    @property
    def communication_fault(self) -> bool:
        """Whether consecutive read failures reached the communication fault limit."""
        return self._communication_fault

    @property
    def safe_stop(self) -> bool:
        """Whether motion commands are blocked due to reported hardware fault status."""
        return self._safe_stop

    @property
    def feedback_age(self) -> Optional[float]:
        """Seconds since the last successful feedback read, or None if never read."""
        if self.last_read_time is None:
            return None
        return time.time() - self.last_read_time

    def synchronize_command_state(self) -> List[int]:
        """Sync the incremental command cache from ANGLE_ACT."""
        actual = self.read_angle()
        self._last_commanded_angle = list(actual)
        self._last_actual_angle = list(actual)
        self._current_frame = self._last_commanded_angle
        return actual

    # ==================================================================
    #  Internal: read 16-bit registers (with retry)
    # ==================================================================
    def _read_reg16(self, addr: int, count: int) -> bytes:
        """Read 16-bit registers and return raw data bytes.

        Parameters
        ----------
        addr : int
            Starting register address.
        count : int
            Number of 16-bit registers to read.

        Returns
        -------
        bytes
            Raw data (count x 2 bytes).

        Raises
        ------
        RH56TimeoutError
            All retries exhausted.
        """
        register_length = count * 2
        request_frame = build_read_reg16(self._node_id, addr, register_length)

        last_exc: Optional[Exception] = None
        for attempt in range(1 + self._config.retry.retries):
            try:
                response = self._transport.request(
                    request_frame,
                    timeout=self._config.retry.timeout,
                )
                data = parse_read_response(
                    response, self._node_id, addr, register_length
                )
                self._record_read_success()
                return data
            except (RH56TimeoutError, RH56ProtocolError) as exc:
                last_exc = exc
                logger.debug(
                    "Read reg 0x%04X attempt %d failed: %s",
                    addr, attempt + 1, exc,
                )
                if attempt < self._config.retry.retries:
                    time.sleep(self._config.retry.retry_delay)

        self._record_read_failure(last_exc)
        raise RH56TimeoutError(
            f"Read reg 0x{addr:04X} failed after {1 + self._config.retry.retries} attempts: "
            f"{last_exc}"
        ) from last_exc

    # ==================================================================
    #  Internal: read byte-array registers (with retry)
    # ==================================================================
    def _read_bytes(self, addr: int, length: int) -> bytes:
        """Read byte-array registers (ERROR / STATUS / TEMP).

        *length* is the number of data bytes.
        """
        request_frame = build_read_reg16(self._node_id, addr, length)

        last_exc: Optional[Exception] = None
        for attempt in range(1 + self._config.retry.retries):
            try:
                response = self._transport.request(
                    request_frame,
                    timeout=self._config.retry.timeout,
                )
                data = parse_read_response(
                    response, self._node_id, addr, length
                )
                self._record_read_success()
                return data
            except (RH56TimeoutError, RH56ProtocolError) as exc:
                last_exc = exc
                logger.debug(
                    "Read bytes 0x%04X attempt %d failed: %s",
                    addr, attempt + 1, exc,
                )
                if attempt < self._config.retry.retries:
                    time.sleep(self._config.retry.retry_delay)

        self._record_read_failure(last_exc)
        raise RH56TimeoutError(
            f"Read bytes 0x{addr:04X} failed after {1 + self._config.retry.retries} attempts: "
            f"{last_exc}"
        ) from last_exc

    # ==================================================================
    #  Internal: write registers
    # ==================================================================
    def _write_reg16(
        self, addr: int, data: List[int], wait_ack: bool = True
    ) -> None:
        """Build and send a write frame. Optionally wait for ACK.

        Raises
        ------
        RH56ValidationError
            Address is None.
        RH56NotConnectedError
            Serial port not connected.
        """
        if addr is None:
            raise RH56ValidationError(
                "Register address is None; check registers.py configuration"
            )
        if not self.is_connected:
            raise RH56NotConnectedError("Serial port not connected")
        self._refresh_calibration_state()
        if self.is_calibrating:
            raise RH56BusyError("RH56 is calibrating; 16-bit write rejected")

        frame = build_reg16_frame(self._node_id, addr, data)
        try:
            if wait_ack and not self._transport.is_mock:
                ack = self._transport.request(frame, timeout=self._config.retry.timeout)
                RH56Protocol.parse_write_ack(ack, self._node_id, addr)
            else:
                self._transport.write(frame)
        except Exception:
            logger.exception("Write reg 0x%04X failed", addr)
            raise

        self.last_command = {
            "timestamp": time.time(),
            "addr": addr,
            "data": list(data),
            "wait_ack": wait_ack,
        }

    def _write_u8(self, addr: int, value: int, wait_ack: bool = True) -> None:
        """Write one byte to a maintenance register."""
        if addr is None:
            raise RH56ValidationError(
                "Register address is None; check registers.py configuration"
            )
        if not self.is_connected:
            raise RH56NotConnectedError("Serial port not connected")
        if not 0 <= int(value) <= 0xFF:
            raise RH56ValidationError(f"u8 value out of range: {value}")

        frame = build_write_bytes_frame(self._node_id, addr, bytes([int(value)]))
        try:
            if wait_ack and not self._transport.is_mock:
                ack = self._transport.request(frame, timeout=self._config.retry.timeout)
                RH56Protocol.parse_write_ack(ack, self._node_id, addr)
            else:
                self._transport.write(frame)
        except Exception:
            logger.exception("Write u8 reg 0x%04X failed", addr)
            raise

        self.last_command = {
            "timestamp": time.time(),
            "addr": addr,
            "data": [int(value)],
            "wait_ack": wait_ack,
            "width": "u8",
        }

    # ==================================================================
    #  Internal: parameter validation
    # ==================================================================
    @staticmethod
    def _validate_servo_list(values: List[int], label: str) -> None:
        """Validate length and basic type of a 6-element servo parameter list."""
        if len(values) != SERVO_COUNT:
            raise RH56ValidationError(
                f"{label} must have exactly {SERVO_COUNT} values, got {len(values)}"
            )
        for i, v in enumerate(values):
            if not isinstance(v, (int, float)):
                raise RH56ValidationError(
                    f"{label}[{i}] type error: {type(v).__name__}"
                )

    # ==================================================================
    #  Internal: diagnostic and safety state
    # ==================================================================
    def _record_read_success(self) -> None:
        self._miss_count = 0
        self._communication_fault = False
        self.last_read_time = time.time()
        if self.last_error and self.last_error.startswith("Read failed"):
            self.last_error = None

    def _record_read_failure(self, exc: Optional[Exception]) -> None:
        self._miss_count += 1
        self.last_error = f"Read failed: {exc}"
        if self._miss_count >= self._max_miss_before_fault:
            self._communication_fault = True

    def _record_feedback(self, key: str, value: object) -> None:
        self.last_feedback[key] = value
        self.last_read_time = time.time()

    def _update_safe_stop_from_status(self, status: List[int]) -> None:
        fault_codes = {5, 6, 7}
        if any(code in fault_codes for code in status):
            self._safe_stop = True
            self.last_error = f"Fault status reported: {status}"

    def _refresh_calibration_state(self) -> None:
        if (
            self.is_calibrating
            and self._calibration_busy_until is not None
            and time.monotonic() >= self._calibration_busy_until
        ):
            self.is_calibrating = False
            self._calibration_busy_until = None

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise RH56NotConnectedError("Serial port not connected")

    # ==================================================================
    #  Context manager
    # ==================================================================
    def __enter__(self) -> "RH56Driver":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
        return None

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        stale = ", stale" if self.is_stale else ""
        return (
            f"<RH56Driver port={self._transport._port} "
            f"node={self._node_id} {status}{stale}>"
        )
