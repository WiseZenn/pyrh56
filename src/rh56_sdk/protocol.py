"""
RH56 6-DOF dexterous hand serial bus protocol codec (checked against manual V1.09).

Frame Format
============

**Request** (Host -> RH56)::

    EB 90  ID  Len  CMD  ...Payload...  Checksum

**Response** (RH56 -> Host)::

    90 EB  ID  Len  CMD  ...Payload...  Checksum

- ``Len`` = CMD byte + Payload byte count.
- ``Checksum`` = low 8 bits of the sum of all bytes after the frame header.
- All 16-bit data is **little-endian** (low byte first).
"""

from collections.abc import Sequence

from .exceptions import (
    RH56ChecksumError,
    RH56FrameError,
    RH56ProtocolError,
)


class RH56Protocol:
    """RH56 private protocol constants and static factory methods."""

    # Frame headers: request and response headers are reversed.
    # Do not mix them up during parsing.
    HEADER_REQ = bytes([0xEB, 0x90])  # Host -> RH56
    HEADER_RESP = bytes([0x90, 0xEB])  # RH56 -> Host

    # Command bytes: 0x11 reads registers, 0x12 writes registers
    # in the RH56 private protocol.
    CMD_READ = 0x11  # RS232/RS485 private protocol read register
    CMD_WRITE = 0x12  # RS232/RS485 private protocol write register
    MAX_WRITE_BYTE_PAYLOAD = 252
    MAX_REG16_WRITE_COUNT = 126

    @staticmethod
    def validate_node_id(node_id: int) -> int:
        if isinstance(node_id, bool) or not isinstance(node_id, int):
            raise RH56ProtocolError("node_id must be int")
        if not 0 <= node_id <= 0xFF:
            raise RH56ProtocolError(f"node_id out of range: {node_id}")
        return node_id

    @staticmethod
    def validate_address(addr: int) -> int:
        if isinstance(addr, bool) or not isinstance(addr, int):
            raise RH56ProtocolError("address must be int")
        if not 0 <= addr <= 0xFFFF:
            raise RH56ProtocolError(f"address out of range: {addr}")
        return addr

    @staticmethod
    def validate_u16_value(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RH56ProtocolError(f"u16 register value must be int, got {type(value).__name__}")
        if not 0 <= value <= 0xFFFF:
            raise RH56ProtocolError(f"u16 register value out of range: {value}")
        return value

    # ------------------------------------------------------------------
    #  Checksum
    # ------------------------------------------------------------------
    @staticmethod
    def checksum(data: bytes) -> int:
        """Compute low 8-bit sum of all bytes in *data* (everything after header)."""
        # Checksum is computed over bytes after the header and keeps only
        # the low 8 bits.
        return sum(data) & 0xFF

    # ==================================================================
    #  Write frame builder
    # ==================================================================
    @staticmethod
    def build_reg16_frame(node_id: int, addr: int, data: Sequence[int]) -> bytes:
        """Build a 16-bit register batch-write frame.

        Frame structure::

            EB 90  ID  Len  12  Addr_L Addr_H  Data...  Checksum

        Parameters
        ----------
        node_id : int
            Node ID (RH56 default 1).
        addr : int
            Starting register address (16-bit).
        data : list[int]
            16-bit values to write.
        """
        node_id = RH56Protocol.validate_node_id(node_id)
        addr = RH56Protocol.validate_address(addr)
        if len(data) < 1:
            raise RH56ProtocolError("reg16 payload must not be empty")
        if len(data) > RH56Protocol.MAX_REG16_WRITE_COUNT:
            raise RH56ProtocolError(
                f"reg16 payload too long: {len(data)}, maximum={RH56Protocol.MAX_REG16_WRITE_COUNT}"
            )

        # Register address and 16-bit data are little-endian:
        # low byte first, high byte second.
        payload = bytearray([addr & 0xFF, (addr >> 8) & 0xFF])
        for v in data:
            value = RH56Protocol.validate_u16_value(v)
            payload.extend([value & 0xFF, (value >> 8) & 0xFF])

        # Len = CMD + Payload length, excluding header, ID, Len itself,
        # and checksum.
        body = bytes([node_id, len(payload) + 1, RH56Protocol.CMD_WRITE]) + bytes(payload)
        return RH56Protocol.HEADER_REQ + body + bytes([RH56Protocol.checksum(body)])

    @staticmethod
    def build_write_bytes_frame(node_id: int, addr: int, data: bytes) -> bytes:
        """Build a byte-register write frame.

        Use this for byte-sized maintenance registers such as CLEAR_ERROR,
        SAVE, RESET_PARA, GESTURE_NO_SET, and GESTURE_FORCE_CLB.
        """
        if not data:
            raise RH56ProtocolError("write byte payload must not be empty")
        if len(data) > RH56Protocol.MAX_WRITE_BYTE_PAYLOAD:
            raise RH56ProtocolError(
                f"write byte payload too long: {len(data)}, "
                f"maximum={RH56Protocol.MAX_WRITE_BYTE_PAYLOAD}"
            )

        node_id = RH56Protocol.validate_node_id(node_id)
        addr = RH56Protocol.validate_address(addr)
        payload = bytearray([addr & 0xFF, (addr >> 8) & 0xFF])
        payload.extend(data)
        body = bytes([node_id, len(payload) + 1, RH56Protocol.CMD_WRITE]) + bytes(payload)
        return RH56Protocol.HEADER_REQ + body + bytes([RH56Protocol.checksum(body)])

    # ==================================================================
    #  Read frame builder
    # ==================================================================
    @staticmethod
    def build_read_reg16(node_id: int, addr: int, register_length: int) -> bytes:
        """Build a read-register request frame.

        Frame structure::

            EB 90  ID  04  11  Addr_L Addr_H  RegLen  Checksum

        Always 9 bytes total.

        Parameters
        ----------
        node_id : int
            Node ID.
        addr : int
            Starting register address (16-bit).
        register_length : int
            Number of **data bytes** to read (e.g. 12 for 6 shorts).
        """
        if isinstance(register_length, bool) or not isinstance(register_length, int):
            raise RH56ProtocolError("register_length must be int")
        if register_length < 1 or register_length > 255:
            raise RH56ProtocolError(f"Register length out of range: {register_length}")

        node_id = RH56Protocol.validate_node_id(node_id)
        addr = RH56Protocol.validate_address(addr)
        # Read-register request: fixed 4-byte length field:
        # CMD + Addr_L + Addr_H + RegLen.
        body = bytes(
            [
                node_id,
                0x04,
                RH56Protocol.CMD_READ,
                addr & 0xFF,
                (addr >> 8) & 0xFF,
                register_length,
            ]
        )
        return RH56Protocol.HEADER_REQ + body + bytes([RH56Protocol.checksum(body)])

    # ==================================================================
    #  Response parsers
    # ==================================================================
    @staticmethod
    def parse_read_response(
        response: bytes,
        node_id: int,
        addr: int,
        register_length: int,
    ) -> bytes:
        """Strictly validate a read-register response and return raw data bytes.

        Expected response::

            90 EB  ID  RegLen+3  11  Addr_L Addr_H  Data...  Checksum

        Total length = register_length + 8 bytes.

        Returns
        -------
        bytes
            Pure data payload (address and checksum stripped).

        Raises
        ------
        RH56FrameError
            Header, length, command, or address mismatch.
        RH56ChecksumError
            Checksum mismatch.
        """
        node_id = RH56Protocol.validate_node_id(node_id)
        addr = RH56Protocol.validate_address(addr)
        expected_len = register_length + 8

        # Strict mode: length, header, node ID, command, echoed address,
        # and checksum must all match.
        if len(response) != expected_len:
            raise RH56FrameError(
                f"Response length mismatch: expected {expected_len}, got {len(response)}"
            )

        # Header
        if response[0] != 0x90 or response[1] != 0xEB:
            raise RH56FrameError(
                f"Invalid response header: expected 90 EB, got {response[0]:02X} {response[1]:02X}"
            )

        # Node ID
        if response[2] != node_id:
            raise RH56FrameError(f"Node ID mismatch: expected {node_id}, got {response[2]}")

        # Length field
        expected_len_field = register_length + 3
        if response[3] != expected_len_field:
            raise RH56FrameError(
                f"Length field mismatch: expected {expected_len_field}, got {response[3]}"
            )

        # Command byte
        if response[4] != RH56Protocol.CMD_READ:
            raise RH56FrameError(
                f"Invalid response command: expected {RH56Protocol.CMD_READ:02X}, "
                f"got {response[4]:02X}"
            )

        # Echoed address
        # The device echoes the register address in the response
        # so callers can confirm this data belongs to their request.
        resp_addr = response[5] | (response[6] << 8)
        if resp_addr != addr:
            raise RH56FrameError(
                f"Response address mismatch: expected 0x{addr:04X}, got 0x{resp_addr:04X}"
            )

        # Checksum
        expected_cs = sum(response[2:-1]) & 0xFF
        actual_cs = response[-1]
        if actual_cs != expected_cs:
            raise RH56ChecksumError(
                f"Checksum mismatch: computed 0x{expected_cs:02X}, received 0x{actual_cs:02X}"
            )

        # Data: skip [90 EB ID Len CMD Addr_L Addr_H] = 7 header bytes
        # Return the pure data region so upper layers can decode
        # as u16/i16/u8 as needed.
        return response[7:-1]

    @staticmethod
    def parse_write_ack(
        response: bytes,
        node_id: int,
        addr: int,
    ) -> bool:
        """Validate a write-register acknowledgement frame.

        Expected::

            90 EB  ID  04  12  Addr_L Addr_H  01  Checksum

        Returns
        -------
        bool
            True if the ACK is valid.
        """
        node_id = RH56Protocol.validate_node_id(node_id)
        addr = RH56Protocol.validate_address(addr)
        expected_len = 9

        if len(response) != expected_len:
            raise RH56FrameError(
                f"Write ACK length mismatch: expected {expected_len}, got {len(response)}"
            )

        if response[0] != 0x90 or response[1] != 0xEB:
            raise RH56FrameError("Invalid write ACK header")

        if response[2] != node_id:
            raise RH56FrameError("Write ACK node ID mismatch")

        if response[3] != 0x04:
            raise RH56FrameError("Write ACK length field mismatch")

        if response[4] != RH56Protocol.CMD_WRITE:
            raise RH56FrameError("Write ACK command byte mismatch")

        # Write ACK also echoes the starting address to avoid
        # mistaking another register's response for success.
        resp_addr = response[5] | (response[6] << 8)
        if resp_addr != addr:
            raise RH56FrameError("Write ACK address mismatch")

        result = response[7]
        if result != 0x01:
            raise RH56ProtocolError(
                f"Write rejected by RH56: address=0x{addr:04X}, result=0x{result:02X}"
            )

        expected_cs = sum(response[2:-1]) & 0xFF
        if response[-1] != expected_cs:
            raise RH56ChecksumError("Write ACK checksum mismatch")

        return True

    # ==================================================================
    #  Generic response parser (backward-compatible)
    # ==================================================================
    @staticmethod
    def parse_response(response: bytes) -> tuple[int, int, list[int]]:
        """Generic response frame parser.

        Returns ``(node_id, cmd, values)`` where values is a list of 16-bit ints.
        Prefer ``parse_read_response`` for strict validation in new code.
        """
        if len(response) < 5:
            raise RH56FrameError(f"Response too short: {len(response)} bytes")

        # Compatibility: historically this accepted both request and
        # response frame headers.
        if not (
            (response[0] == 0xEB and response[1] == 0x90)
            or (response[0] == 0x90 and response[1] == 0xEB)
        ):
            raise RH56FrameError(f"Invalid header: {response[0]:02X} {response[1]:02X}")

        node_id = response[2]
        length = response[3]
        cmd = response[4]

        checksum_index = 4 + length
        if len(response) < checksum_index + 1:
            raise RH56FrameError(
                f"Frame truncated: expected {checksum_index + 1}, got {len(response)}"
            )

        expected = sum(response[2:checksum_index]) & 0xFF
        actual = response[checksum_index]
        if expected != actual:
            raise RH56ChecksumError(f"Checksum: computed 0x{expected:02X}, received 0x{actual:02X}")

        # The generic parser does not validate address semantics.
        # It converts bytes after CMD to unsigned 16-bit integers (LE).
        data_bytes = response[5:checksum_index]
        values = RH56Protocol.parse_reg16_values(data_bytes)
        return node_id, cmd, values

    # ==================================================================
    #  Value decoders
    # ==================================================================
    @staticmethod
    def parse_reg16_values(data: bytes) -> list[int]:
        """Decode byte sequence into unsigned 16-bit integers (LE)."""
        values: list[int] = []
        for i in range(0, len(data) - 1, 2):
            # Combine two bytes into an unsigned 16-bit integer:
            # low byte | high byte << 8.
            values.append(data[i] | (data[i + 1] << 8))
        return values

    @staticmethod
    def parse_u16_le(data: bytes, count: int = 6) -> list[int]:
        """Parse unsigned 16-bit little-endian array.

        Raises
        ------
        ValueError
            If ``len(data) != count * 2``.
        """
        expected = count * 2
        if len(data) != expected:
            raise ValueError(f"Expected {expected} bytes, got {len(data)}")
        return [data[2 * i] | (data[2 * i + 1] << 8) for i in range(count)]

    @staticmethod
    def parse_i16_le(data: bytes, count: int = 6) -> list[int]:
        """Parse signed 16-bit little-endian array (supports -1 etc.)."""
        expected = count * 2
        if len(data) != expected:
            raise ValueError(f"Expected {expected} bytes, got {len(data)}")
        values = []
        for i in range(count):
            raw = data[2 * i] | (data[2 * i + 1] << 8)
            if raw >= 0x8000:
                # Two's complement to signed: e.g., 0xFFFF → -1.
                raw -= 0x10000
            values.append(raw)
        return values

    @staticmethod
    def parse_u8(data: bytes, count: int = 6) -> list[int]:
        """Parse unsigned 8-bit array."""
        if len(data) != count:
            raise ValueError(f"Expected {count} bytes, got {len(data)}")
        return list(data)


# ==================================================================
#  Module-level convenience functions (compatible with core.py)
# ==================================================================
def build_reg16_frame(node_id: int, addr: int, data: Sequence[int]) -> bytes:
    return RH56Protocol.build_reg16_frame(node_id, addr, data)


def build_write_reg16_frame(node_id: int, addr: int, data: Sequence[int]) -> bytes:
    return RH56Protocol.build_reg16_frame(node_id, addr, data)


def build_write_bytes_frame(node_id: int, addr: int, data: bytes) -> bytes:
    return RH56Protocol.build_write_bytes_frame(node_id, addr, data)


def build_read_reg16(node_id: int, addr: int, register_length: int) -> bytes:
    return RH56Protocol.build_read_reg16(node_id, addr, register_length)


def build_read_frame(node_id: int, addr: int, register_length: int) -> bytes:
    return RH56Protocol.build_read_reg16(node_id, addr, register_length)


def parse_response(response: bytes) -> tuple[int, int, list[int]]:
    return RH56Protocol.parse_response(response)


def parse_reg16_values(data: bytes) -> list[int]:
    return RH56Protocol.parse_reg16_values(data)


def parse_read_response(response: bytes, node_id: int, addr: int, register_length: int) -> bytes:
    return RH56Protocol.parse_read_response(response, node_id, addr, register_length)


def parse_u16_le(data: bytes, count: int = 6) -> list[int]:
    return RH56Protocol.parse_u16_le(data, count)


def parse_i16_le(data: bytes, count: int = 6) -> list[int]:
    return RH56Protocol.parse_i16_le(data, count)


def parse_u8(data: bytes, count: int = 6) -> list[int]:
    return RH56Protocol.parse_u8(data, count)
