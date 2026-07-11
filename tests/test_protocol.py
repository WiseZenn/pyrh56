import unittest

from rh56_sdk.exceptions import RH56ChecksumError, RH56FrameError, RH56ProtocolError
from rh56_sdk.protocol import (
    RH56Protocol,
    build_read_frame,
    build_read_reg16,
    build_reg16_frame,
    build_write_bytes_frame,
    build_write_reg16_frame,
    parse_i16_le,
    parse_read_response,
    parse_u16_le,
)
from rh56_sdk.registers import REG_ANGLE_ACT, REG_ANGLE_SET
from rh56_sdk.registers import REG_GESTURE_FORCE_CLB


def _hex(data: bytes) -> str:
    return data.hex(" ").upper()


def _read_response(node_id: int, addr: int, data: bytes) -> bytes:
    body = bytes(
        [
            node_id,
            len(data) + 3,
            RH56Protocol.CMD_READ,
            addr & 0xFF,
            (addr >> 8) & 0xFF,
        ]
    ) + data
    return RH56Protocol.HEADER_RESP + body + bytes([RH56Protocol.checksum(body)])


class ProtocolTests(unittest.TestCase):
    def test_build_read_frame_manual_golden_angle_act(self) -> None:
        frame = build_read_frame(1, REG_ANGLE_ACT, 12)
        self.assertEqual(_hex(frame), "EB 90 01 04 11 0A 06 0C 32")
        self.assertEqual(build_read_reg16(1, REG_ANGLE_ACT, 12), frame)

    def test_build_write_reg16_frame_little_endian(self) -> None:
        frame = build_write_reg16_frame(1, REG_ANGLE_SET, [1000, 900])
        self.assertEqual(_hex(frame), "EB 90 01 07 12 CE 05 E8 03 84 03 5F")
        self.assertEqual(build_reg16_frame(1, REG_ANGLE_SET, [1000, 900]), frame)

    def test_build_write_bytes_frame_for_force_calibration(self) -> None:
        frame = build_write_bytes_frame(1, REG_GESTURE_FORCE_CLB, b"\x01")
        self.assertEqual(_hex(frame), "EB 90 01 04 12 F1 03 01 0C")

    def test_parse_read_response_returns_only_data_payload(self) -> None:
        values = [1000, 1000, 1000, 1000, 700, 900]
        data = b"".join(v.to_bytes(2, "little") for v in values)
        response = _read_response(1, REG_ANGLE_ACT, data)

        parsed = parse_read_response(response, 1, REG_ANGLE_ACT, 12)

        self.assertEqual(parsed, data)
        self.assertEqual(parse_u16_le(parsed, count=6), values)

    def test_parse_read_response_rejects_wrong_address(self) -> None:
        response = _read_response(1, REG_ANGLE_ACT, b"\x00" * 12)

        with self.assertRaises(RH56FrameError):
            parse_read_response(response, 1, REG_ANGLE_ACT + 2, 12)

    def test_parse_write_ack(self) -> None:
        body = bytes([1, 0x04, RH56Protocol.CMD_WRITE, 0xCE, 0x05, 0x01])
        ack = RH56Protocol.HEADER_RESP + body + bytes([RH56Protocol.checksum(body)])

        self.assertEqual(_hex(ack), "90 EB 01 04 12 CE 05 01 EB")
        self.assertTrue(RH56Protocol.parse_write_ack(ack, 1, REG_ANGLE_SET))

    def test_parse_write_ack_rejects_failure_result(self) -> None:
        body = bytes([1, 0x04, RH56Protocol.CMD_WRITE, 0xCE, 0x05, 0x00])
        ack = RH56Protocol.HEADER_RESP + body + bytes([RH56Protocol.checksum(body)])

        with self.assertRaises(RH56ProtocolError):
            RH56Protocol.parse_write_ack(ack, 1, REG_ANGLE_SET)

    def test_write_byte_payload_boundary(self) -> None:
        self.assertIsInstance(build_write_bytes_frame(1, REG_GESTURE_FORCE_CLB, b"\x01" * 252), bytes)
        with self.assertRaises(RH56ProtocolError):
            build_write_bytes_frame(1, REG_GESTURE_FORCE_CLB, b"\x01" * 253)

    def test_reg16_payload_boundary(self) -> None:
        self.assertIsInstance(build_reg16_frame(1, REG_ANGLE_SET, [0] * 126), bytes)
        with self.assertRaises(RH56ProtocolError):
            build_reg16_frame(1, REG_ANGLE_SET, [0] * 127)

    def test_node_id_and_address_are_validated_before_encoding(self) -> None:
        with self.assertRaises(RH56ProtocolError):
            build_read_frame(256, REG_ANGLE_ACT, 12)
        with self.assertRaises(RH56ProtocolError):
            build_read_frame(1, 0x10000, 12)

    def test_checksum_low_8_bits(self) -> None:
        body = bytes([0x01, 0x04, 0x11, 0x0A, 0x06, 0x0C])
        self.assertEqual(RH56Protocol.checksum(body), 0x32)

    def test_checksum_error_is_reported(self) -> None:
        response = bytearray(_read_response(1, REG_ANGLE_ACT, b"\x00" * 12))
        response[-1] ^= 0xFF

        with self.assertRaises(RH56ChecksumError):
            parse_read_response(bytes(response), 1, REG_ANGLE_ACT, 12)

    def test_parse_i16_le_decodes_twos_complement_force_values(self) -> None:
        data = bytes.fromhex("FB FF FC FF 00 00 08 00 00 00 F7 FF")
        self.assertEqual(parse_i16_le(data, count=6), [-5, -4, 0, 8, 0, -9])


if __name__ == "__main__":
    unittest.main()
