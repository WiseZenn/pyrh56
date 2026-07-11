import unittest
import threading
import time

from rh56_sdk.exceptions import RH56ChecksumError, RH56ConnectionError
from rh56_sdk.protocol import RH56Protocol, build_read_frame
from rh56_sdk.registers import REG_ANGLE_ACT
from rh56_sdk.transport import SerialTransport


class FakeSerial:
    def __init__(self, incoming: bytes = b"", response: bytes = b"") -> None:
        self.is_open = True
        self.timeout = 0.1
        self.incoming = bytearray(incoming)
        self.response = response
        self.written = bytearray()
        self.reset_count = 0

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self.reset_count += 1
        self.incoming.clear()

    def flush(self) -> None:
        pass

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        self.incoming.extend(self.response)
        return len(data)

    def read(self, size: int) -> bytes:
        if not self.incoming:
            return b""
        chunk = self.incoming[:size]
        del self.incoming[:size]
        return bytes(chunk)


def _read_response(data: bytes = b"\x00" * 12) -> bytes:
    body = bytes([1, len(data) + 3, RH56Protocol.CMD_READ, 0x0A, 0x06]) + data
    return RH56Protocol.HEADER_RESP + body + bytes([RH56Protocol.checksum(body)])


class TransportTests(unittest.TestCase):
    def test_read_response_frame_scans_past_stale_bytes(self) -> None:
        transport = SerialTransport("COM_FAKE")
        transport._ser = FakeSerial(b"\x00\xFF\x90\x00" + _read_response())

        frame = transport.read_response_frame(timeout=0.1)

        self.assertEqual(frame, _read_response())

    def test_request_clears_input_before_write_and_reads_response(self) -> None:
        response = _read_response()
        fake = FakeSerial(incoming=b"stale", response=response)
        transport = SerialTransport("COM_FAKE")
        transport._ser = fake
        request = build_read_frame(1, REG_ANGLE_ACT, 12)

        frame = transport.request(request, timeout=0.1)

        self.assertEqual(fake.reset_count, 1)
        self.assertEqual(bytes(fake.written), request)
        self.assertEqual(frame, response)

    def test_read_response_frame_rejects_bad_checksum(self) -> None:
        response = bytearray(_read_response())
        response[-1] ^= 0x01
        transport = SerialTransport("COM_FAKE")
        transport._ser = FakeSerial(bytes(response))

        with self.assertRaises(RH56ChecksumError):
            transport.read_response_frame(timeout=0.1)

    def test_short_write_is_wrapped_as_connection_error(self) -> None:
        class ShortWriteSerial(FakeSerial):
            def write(self, data: bytes) -> int:
                return len(data) - 1

        transport = SerialTransport("COM_FAKE")
        transport._ser = ShortWriteSerial()

        with self.assertRaises(RH56ConnectionError):
            transport.write(b"123")

    def test_transport_transactions_are_serialized(self) -> None:
        class SlowSerial(FakeSerial):
            def __init__(self, response: bytes) -> None:
                super().__init__(response=response)
                self.active = 0
                self.max_active = 0
                self.lock = threading.Lock()

            def write(self, data: bytes) -> int:
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                try:
                    time.sleep(0.01)
                    return super().write(data)
                finally:
                    with self.lock:
                        self.active -= 1

        response = _read_response()
        fake = SlowSerial(response=response)
        transport = SerialTransport("COM_FAKE")
        transport._ser = fake
        request = build_read_frame(1, REG_ANGLE_ACT, 12)

        threads = [
            threading.Thread(target=lambda: transport.request(request, timeout=0.2))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(fake.max_active, 1)


if __name__ == "__main__":
    unittest.main()
