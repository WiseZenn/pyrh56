"""
Serial transport layer -- wraps pyserial physical I/O and mock loopback.

Supports
--------
- Real serial port (requires pyserial).
- ``COM_MOCK`` mock port (development/testing without hardware).
"""

import logging
import threading
import time
from typing import List, Optional

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

from .exceptions import (
    RH56ChecksumError,
    RH56ConnectionError,
    RH56FrameError,
    RH56NotConnectedError,
    RH56TimeoutError,
)
from .protocol import RH56Protocol
from .models import SerialPortInfo

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
#  Mock Serial -- in-memory fake serial port for testing
# ------------------------------------------------------------------
class MockSerial:
    """Mock serial port: writes succeed silently, reads return zero bytes."""

    is_open: bool = True

    def close(self) -> None:
        self.is_open = False

    def write(self, data: bytes) -> int:
        return len(data)

    def reset_input_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def read(self, size: int) -> bytes:
        return b"\x00" * size

    @property
    def timeout(self) -> float:
        return 0.1

    @timeout.setter
    def timeout(self, value: float) -> None:
        pass


# ------------------------------------------------------------------
#  SerialTransport
# ------------------------------------------------------------------
class SerialTransport:
    """RH56 serial bus transport abstraction.

    Usage
    -----
    >>> transport = SerialTransport("COM3", 115200)
    >>> if transport.is_connected:
    ...     transport.write(frame)
    """

    def __init__(
        self, port: str, baud: int = 115200, timeout: float = 0.1
    ) -> None:
        self._port = port
        self._baud = baud
        self._timeout = timeout
        self._ser = None  # type: Optional[serial.Serial]
        self._transaction_lock = threading.RLock()

    # ------------------------------------------------------------------
    #  Port enumeration
    # ------------------------------------------------------------------
    @staticmethod
    def list_ports() -> List[str]:
        """Return real serial port names; Mock must be selected explicitly."""
        return [port.device for port in SerialTransport.list_port_info()]

    @staticmethod
    def list_port_info() -> list[SerialPortInfo]:
        """Enumerate serial adapters without opening them or probing hardware."""
        if list_ports is None:
            raise RH56ConnectionError("pyserial is required to enumerate serial ports")
        try:
            return sorted(
                [
                    SerialPortInfo(
                        device=port.device,
                        description=port.description,
                        hwid=port.hwid,
                        vid=port.vid,
                        pid=port.pid,
                        serial_number=port.serial_number,
                        manufacturer=port.manufacturer,
                    )
                    for port in list_ports.comports()
                ],
                key=lambda port: port.device,
            )
        except OSError as exc:
            raise RH56ConnectionError(f"Cannot enumerate serial ports: {exc}") from exc

    # ------------------------------------------------------------------
    #  Connection state
    # ------------------------------------------------------------------
    @property
    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    @property
    def is_mock(self) -> bool:
        """Whether running in mock (no-hardware) mode."""
        return isinstance(self._ser, MockSerial)

    # ------------------------------------------------------------------
    #  Connection management
    # ------------------------------------------------------------------
    def connect(self, port: Optional[str] = None, baud: Optional[int] = None) -> None:
        """Open the serial port. Optional args override constructor defaults."""
        if port is not None:
            self._port = port
        if baud is not None:
            self._baud = baud

        if self.is_connected:
            self.disconnect()

        if self._port == "COM_MOCK":
            logger.info("Connected to Mock Serial (COM_MOCK)")
            self._ser = MockSerial()
            return

        if serial is None:
            raise ImportError("pyserial is not installed. Run: pip install pyserial")

        try:
            self._ser = serial.Serial(
                self._port, self._baud, timeout=self._timeout
            )
            logger.info("Connected to %s @ %d baud", self._port, self._baud)
        except serial.SerialException as exc:
            raise RH56ConnectionError(
                f"Failed to open serial port {self._port}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the serial port."""
        with self._transaction_lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
                finally:
                    self._ser = None
                    logger.info("Disconnected")

    # ------------------------------------------------------------------
    #  Atomic read / write
    # ------------------------------------------------------------------
    def write(self, data: bytes) -> None:
        """Write raw bytes to the serial port."""
        with self._transaction_lock:
            self._write_all_unlocked(data)

    def _write_all_unlocked(self, data: bytes) -> None:
        """Write all bytes while the caller holds the transaction lock."""
        if not self._ser:
            raise RH56NotConnectedError("Serial port not connected")
        try:
            written = self._ser.write(data)
            if written is not None and written != len(data):
                raise RH56ConnectionError(
                    f"Short serial write: expected {len(data)}, wrote {written}"
                )
        except (RH56ConnectionError, RH56NotConnectedError):
            raise
        except Exception as exc:
            raise RH56ConnectionError(
                f"Serial write failed on {self._port}: {exc}"
            ) from exc

    def read(self, size: int, timeout: Optional[float] = None) -> bytes:
        """Read *size* bytes from the serial port."""
        if not self._ser:
            raise RH56NotConnectedError("Serial port not connected")

        original_timeout = self._ser.timeout
        if timeout is not None:
            self._ser.timeout = timeout

        try:
            data = self._ser.read(size)
            if len(data) < size:
                logger.warning(
                    "Short read: expected %d bytes, got %d", size, len(data)
                )
            return data
        except (RH56ConnectionError, RH56NotConnectedError):
            raise
        except Exception as exc:
            raise RH56ConnectionError(
                f"Serial read failed on {self._port}: {exc}"
            ) from exc
        finally:
            self._ser.timeout = original_timeout

    # ------------------------------------------------------------------
    #  Request-response (protocol-aware)
    # ------------------------------------------------------------------
    def request(self, frame: bytes, timeout: Optional[float] = None) -> bytes:
        """Send a request frame and read the complete response.

        - Mock mode: synthesizes a valid zero-data response from the request.
        - Real mode: clears stale input, writes request, scans for ``90 EB``,
          then reads exactly one complete response frame.
        """
        with self._transaction_lock:
            if not self._ser:
                raise RH56NotConnectedError("Serial port not connected")

            # Mock: synthesize a valid zero-data response
            if isinstance(self._ser, MockSerial):
                self._write_all_unlocked(frame)
                return self._build_mock_response(frame)

            self.clear_input_buffer()
            self._write_all_unlocked(frame)
            self._flush_output()
            return self.read_response_frame(timeout=timeout)

    def clear_input_buffer(self) -> None:
        """Discard stale bytes before starting a new request-response cycle."""
        if not self._ser:
            raise RH56NotConnectedError("Serial port not connected")
        reset = getattr(self._ser, "reset_input_buffer", None)
        if reset is None:
            reset = getattr(self._ser, "flushInput", None)
        if reset is not None:
            try:
                reset()
            except Exception as exc:
                logger.debug("Failed to clear input buffer: %s", exc)

    def read_response_frame(self, timeout: Optional[float] = None) -> bytes:
        """Read one complete RH56 response frame from the serial stream.

        The reader scans byte-by-byte until it finds the response header
        ``90 EB``. This tolerates stale bytes, half packets, and request echoes
        before the real response frame.
        """
        if not self._ser:
            raise RH56NotConnectedError("Serial port not connected")

        timeout_s = self._timeout if timeout is None else float(timeout)
        deadline = time.monotonic() + max(0.0, timeout_s)
        header = self._scan_response_header(deadline)
        fields = self._read_exact(2, deadline)
        node_id = fields[0]
        length_field = fields[1]

        if length_field < 1:
            raise RH56FrameError(f"Invalid response length field: {length_field}")

        rest = self._read_exact(length_field + 1, deadline)
        frame = header + bytes([node_id, length_field]) + rest
        self._validate_checksum(frame)
        return frame

    def _scan_response_header(self, deadline: float) -> bytes:
        """Find the ``90 EB`` response header before *deadline*."""
        matched_first = False
        while time.monotonic() < deadline:
            chunk = self._read_with_deadline(1, deadline)
            if not chunk:
                continue

            byte = chunk[0]
            if not matched_first:
                matched_first = byte == RH56Protocol.HEADER_RESP[0]
                continue

            if byte == RH56Protocol.HEADER_RESP[1]:
                return RH56Protocol.HEADER_RESP

            # If this byte is also 0x90, keep it as the first byte of a new
            # possible header; otherwise restart scanning.
            matched_first = byte == RH56Protocol.HEADER_RESP[0]

        raise RH56TimeoutError("Timed out waiting for response header 90 EB")

    def _read_exact(self, size: int, deadline: float) -> bytes:
        """Read exactly *size* bytes before *deadline* or raise timeout."""
        data = bytearray()
        while len(data) < size and time.monotonic() < deadline:
            chunk = self._read_with_deadline(size - len(data), deadline)
            if chunk:
                data.extend(chunk)
        if len(data) != size:
            raise RH56TimeoutError(
                f"Timed out reading response frame: expected {size} bytes, "
                f"got {len(data)}"
            )
        return bytes(data)

    def _read_with_deadline(self, size: int, deadline: float) -> bytes:
        """Read up to *size* bytes using only the remaining timeout budget."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return b""

        assert self._ser is not None  # caller holds lock & connection check
        original_timeout = self._ser.timeout
        self._ser.timeout = remaining
        try:
            return self._ser.read(size)
        except (RH56ConnectionError, RH56NotConnectedError):
            raise
        except Exception as exc:
            raise RH56ConnectionError(
                f"Serial read failed on {self._port}: {exc}"
            ) from exc
        finally:
            self._ser.timeout = original_timeout

    @staticmethod
    def _validate_checksum(frame: bytes) -> None:
        """Validate RH56 checksum over bytes after the two-byte header."""
        expected = sum(frame[2:-1]) & 0xFF
        actual = frame[-1]
        if actual != expected:
            raise RH56ChecksumError(
                f"Checksum mismatch: computed 0x{expected:02X}, "
                f"received 0x{actual:02X}"
            )

    def _flush_output(self) -> None:
        flush = getattr(self._ser, "flush", None)
        if flush is not None:
            try:
                flush()
            except Exception as exc:
                logger.debug("Failed to flush serial output: %s", exc)

    # ------------------------------------------------------------------
    #  Mock response synthesis
    # ------------------------------------------------------------------
    def _build_mock_response(self, request_frame: bytes) -> bytes:
        """Build a valid zero-data response from a request frame (mock mode)."""
        node_id = request_frame[2]
        cmd = request_frame[4]

        if cmd == RH56Protocol.CMD_READ:
            # Read response: 90 EB ID RegLen+3 11 Addr_L Addr_H Data CS
            reg_len = request_frame[7]
            addr_l = request_frame[5]
            addr_h = request_frame[6]
            data = b"\x00" * reg_len
            body = bytes([node_id, reg_len + 3, cmd, addr_l, addr_h]) + data
            cs = sum(body) & 0xFF
            return RH56Protocol.HEADER_RESP + body + bytes([cs])

        if cmd == RH56Protocol.CMD_WRITE:
            # Write ACK: 90 EB ID 04 12 Addr_L Addr_H 01 CS
            addr_l = request_frame[5]
            addr_h = request_frame[6]
            body = bytes([node_id, 0x04, cmd, addr_l, addr_h, 0x01])
            cs = sum(body) & 0xFF
            return RH56Protocol.HEADER_RESP + body + bytes([cs])

        # Unknown command: return minimal valid frame
        body = bytes([node_id, 0x01, cmd])
        cs = sum(body) & 0xFF
        return RH56Protocol.HEADER_RESP + body + bytes([cs])
