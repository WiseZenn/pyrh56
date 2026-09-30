"""Regression checks for SDK behavior used by terminal and script clients."""

import json
from unittest.mock import patch

import pytest

from rh56_sdk import (
    CONSERVATIVE_LIMITS,
    DEFAULT_LIMITS,
    FACTORY_LIMITS,
    HandLimits,
    RH56Config,
    RH56Driver,
    RetryPolicy,
)
from rh56_sdk.calibration import ForceCalibration
from rh56_sdk.configuration import FaultPolicy, JointLimit
from rh56_sdk.constants import RH56_OPEN_FRAME
from rh56_sdk.exceptions import RH56HardwareError, RH56TimeoutError, RH56ValidationError
from rh56_sdk.protocol import RH56Protocol
from rh56_sdk.registers import REG_SPEED_SET
from rh56_sdk.safety import apply_thumb_limit, clamp_frame, validate_frame
from rh56_sdk.transport import SerialTransport


@pytest.mark.parametrize(
    "changes",
    [
        {"port": ""},
        {"node_id": 0},
        {"node_id": 255},
        {"node_id": True},
        {"baud": True},
        {"baud": 9600},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
    ],
)
def test_config_rejects_invalid_values(changes):
    config = {"port": "COM_MOCK", **changes}
    with pytest.raises(RH56ValidationError):
        RH56Config(**config)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: JointLimit(500, 200),
        lambda: JointLimit(True, 1000),
        lambda: RetryPolicy(retries=-1),
        lambda: RetryPolicy(retries=True),
        lambda: RetryPolicy(retry_delay=-0.1),
        lambda: FaultPolicy(stale_after=5, fault_after=3),
    ],
)
def test_invalid_policies_fail_at_construction(factory):
    with pytest.raises(RH56ValidationError):
        factory()


@pytest.mark.parametrize(
    "retry, expected", [(RetryPolicy(), 0.35), (RetryPolicy(timeout=0.07), 0.07)]
)
def test_request_timeout_is_used_for_reads_and_writes(retry, expected):
    hand = RH56Driver(RH56Config("COM_MOCK", timeout=0.35, retry=retry))
    hand.connect(verify=False)
    with patch.object(hand._transport, "request", wraps=hand._transport.request) as request:
        hand.read_angle()
        hand.move_to(RH56_OPEN_FRAME)
        hand.clear_error(settle_time=0)
    assert all(call.kwargs["timeout"] == expected for call in request.call_args_list)
    hand.disconnect()


@pytest.mark.parametrize("index, value", [(True, 500), (1.5, 500), (3, True), (3, float("nan"))])
def test_single_finger_rejects_values_without_silent_conversion(index, value):
    with RH56Driver.mock() as hand:
        hand.move_to(RH56_OPEN_FRAME)
        last_command = hand.last_command
        with pytest.raises(RH56ValidationError):
            hand.move_finger(index, value)
        assert hand.last_command == last_command


def test_single_finger_uses_the_same_rounding_as_full_frame():
    with RH56Driver.mock() as hand:
        hand.move_to(RH56_OPEN_FRAME)
        hand.move_finger(3, 600.6)
        assert hand.commanded_angle[3] == 601
        copied = hand.commanded_angle
        copied[3] = 0
        assert hand.commanded_angle[3] == 601


def test_default_thumb_accepts_full_open_across_public_validation_paths():
    frame = [1000, 1000, 1000, 1000, 1000, 900]
    assert RH56Config("COM_MOCK").limits.thumb_flex.maximum == 1000
    assert HandLimits().thumb_flex.maximum == 1000
    assert RH56Config("COM_MOCK").limits.thumb_flex.minimum == 0
    assert FACTORY_LIMITS.thumb_flex.minimum == 200
    validate_frame(frame)
    assert apply_thumb_limit(frame) == frame
    assert clamp_frame(frame) == frame
    with RH56Driver.mock() as hand:
        hand.move_to(frame)
        assert hand.commanded_angle == frame
        hand.move_finger(4, 1000, base="hold")
        assert hand.commanded_angle == frame


def test_default_thumb_accepts_full_close_across_public_validation_paths():
    frame = [0, 0, 0, 0, 0, 900]
    validate_frame(frame)
    assert apply_thumb_limit(frame) == frame
    assert clamp_frame(frame) == frame
    with RH56Driver.mock() as hand:
        hand.move_to(frame)
        hand.move_finger(4, 0, base="hold")
        assert hand.commanded_angle == frame


@pytest.mark.parametrize(
    "limits, minimum, maximum",
    [
        (DEFAULT_LIMITS, 0, 1000),
        (CONSERVATIVE_LIMITS, 200, 700),
        (FACTORY_LIMITS, 200, 1000),
    ],
)
def test_open_close_presets_respect_selected_thumb_limits(limits, minimum, maximum):
    with RH56Driver(RH56Config("COM_MOCK", limits=limits)) as hand:
        hand.open_hand()
        assert hand.commanded_angle == [1000, 1000, 1000, 1000, maximum, 900]
        hand.close()
        assert hand.commanded_angle == [0, 0, 0, 0, minimum, 900]
        if maximum == 700:
            with pytest.raises(RH56ValidationError):
                hand.move_to([1000, 1000, 1000, 1000, 1000, 900])


@pytest.mark.parametrize("thumb", [-1, 1001])
def test_default_thumb_boundaries_still_reject_outside_values(thumb):
    with RH56Driver.mock() as hand:
        with patch.object(hand._transport, "request") as request:
            with pytest.raises(RH56ValidationError):
                hand.move_finger(4, thumb, base="hold")
        request.assert_not_called()


def test_readiness_refreshes_device_faults_and_latches_stop():
    with RH56Driver.mock() as hand:
        with patch.object(hand, "read_error", return_value=[1, 0, 0, 0, 0, 0]):
            with pytest.raises(RH56HardwareError):
                hand.check_motion_ready()
        with pytest.raises(RH56HardwareError):
            hand.move_to(RH56_OPEN_FRAME)
        hand.clear_error(settle_time=0)
        hand.check_motion_ready()


def test_wait_uses_feedback_and_detects_faults():
    with RH56Driver.mock() as hand:
        with patch.object(hand, "read_angle", return_value=RH56_OPEN_FRAME):
            assert hand.wait_until_reached(RH56_OPEN_FRAME) == RH56_OPEN_FRAME
        with patch.object(hand, "read_status", return_value=[6, 0, 0, 0, 0, 0]):
            with pytest.raises(RH56HardwareError):
                hand.wait_until_reached(RH56_OPEN_FRAME)


def test_force_reached_status_is_not_angle_success():
    with RH56Driver.mock() as hand:
        with patch.object(hand, "read_status", return_value=[3] * 6):
            with pytest.raises(RH56TimeoutError):
                hand.wait_until_reached(RH56_OPEN_FRAME, timeout=0.002, interval=0.001)


def test_late_feedback_cannot_turn_an_expired_wait_into_success():
    with RH56Driver.mock() as hand:
        with patch.object(hand, "read_angle", return_value=RH56_OPEN_FRAME):
            with patch("rh56_sdk.driver.time.monotonic", side_effect=[0.0, 0.0, 2.0]):
                with pytest.raises(RH56TimeoutError):
                    hand.wait_until_reached(RH56_OPEN_FRAME, timeout=1.0)


def test_stop_works_while_calibrating_and_checks_ack():
    with RH56Driver.mock() as hand:
        hand.is_calibrating = True
        with patch.object(hand._transport, "request", wraps=hand._transport.request) as request:
            hand.stop_motion()
        assert request.call_count == 1
        assert hand.last_command["addr"] == REG_SPEED_SET
        assert hand.last_command["data"] == [0] * 6


def test_bad_write_ack_does_not_update_target_cache():
    with RH56Driver.mock() as hand:
        before = hand.commanded_angle
        with patch.object(
            RH56Protocol, "parse_write_ack", side_effect=RH56HardwareError("rejected")
        ):
            with pytest.raises(RH56HardwareError):
                hand.move_to(RH56_OPEN_FRAME)
        assert hand.commanded_angle == before


@pytest.mark.parametrize("offset", [[True] * 6, [1.5] * 6, ["1"] * 6, [32768] * 6, [1] * 5])
def test_calibration_profile_rejects_invalid_offsets_atomically(tmp_path, offset):
    hand = RH56Driver.mock()
    hand.force_zero_offset = [7] * 6
    profile = tmp_path / "baseline.json"
    profile.write_text(json.dumps({"force_zero_offset": offset}), encoding="utf-8")
    with pytest.raises(RH56ValidationError):
        ForceCalibration(hand).load_profile(profile)
    assert hand.force_zero_offset == [7] * 6


@pytest.mark.parametrize("payload", ["[1,2]", "bad json"])
def test_calibration_profile_rejects_wrong_json_shape(tmp_path, payload):
    path = tmp_path / "baseline.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(RH56ValidationError):
        ForceCalibration(RH56Driver.mock()).load_profile(path)


def test_baseline_validation_can_apply_loaded_offset():
    with RH56Driver.mock() as hand:
        hand.force_zero_offset = [50] * 6
        with patch.object(hand, "read_force", return_value=[50] * 6):
            calibration = ForceCalibration(hand)
            assert not calibration.validate_baseline(samples=1, interval=0, tolerance=5)["ok"]
            report = calibration.validate_baseline(
                samples=1, interval=0, tolerance=5, use_offset=True
            )
            assert report["ok"]
            assert report["median"] == [0] * 6


def test_interrupted_calibration_preserves_exclusive_state():
    with RH56Driver.mock() as hand:
        with patch("rh56_sdk.calibration.time.sleep", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                ForceCalibration(hand).run_official(require_confirm=False)
        assert hand.is_calibrating
        assert hand._calibration_busy_until is not None


def test_uncertain_calibration_ack_preserves_exclusive_state():
    with RH56Driver.mock() as hand:
        with patch.object(hand, "_write_u8", side_effect=RH56TimeoutError("no ACK")):
            with pytest.raises(RH56TimeoutError):
                ForceCalibration(hand).run_official(require_confirm=False)
        assert hand.is_calibrating


def test_calibration_rejects_fault_status_even_without_error_bits():
    with RH56Driver.mock() as hand:
        with patch("rh56_sdk.calibration.time.sleep"):
            with patch.object(hand, "read_status", return_value=[6] * 6):
                with pytest.raises(RH56HardwareError):
                    ForceCalibration(hand).run_official(require_confirm=False)


def test_calibration_profile_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(RH56ValidationError):
        ForceCalibration(RH56Driver.mock()).load_profile(path)


def test_missing_pyserial_does_not_invent_a_mock_port():
    with patch("rh56_sdk.transport.list_ports", None):
        from rh56_sdk.exceptions import RH56ConnectionError

        with pytest.raises(RH56ConnectionError):
            SerialTransport.list_ports()
