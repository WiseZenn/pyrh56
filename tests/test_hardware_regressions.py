"""Regressions reproduced from COM13 feedback, with no hardware writes in tests."""

import json
from unittest.mock import patch

import pytest

from rh56_sdk import CONSERVATIVE_LIMITS, RH56Config, RH56Driver, cli
from rh56_sdk.exceptions import RH56HardwareError, RH56TimeoutError, RH56ValidationError
from rh56_sdk.protocol import RH56Protocol
from rh56_sdk.registers import REG_ANGLE_SET

ACTUAL_OPEN = [997, 999, 996, 996, 1000, 886]


def test_unknown_device_status_is_not_reported_as_a_pass(capsys):
    hand = RH56Driver.mock()
    with (
        patch.object(cli, "RH56Driver", return_value=hand),
        patch.object(hand, "read_status", return_value=[255] * 6),
    ):
        code = cli.main(["doctor", "--mock", "--json"])
    report = json.loads(capsys.readouterr().out)
    status = next(check for check in report["data"]["checks"] if check["name"] == "status")
    assert status["ok"] is None
    assert status["severity"] == "warning"
    assert code == 0 and report["data"]["health_verified"] is False


def test_cli_single_finger_does_not_depend_on_other_channels_limits(capsys):
    hand = RH56Driver(RH56Config("COM_MOCK", limits=CONSERVATIVE_LIMITS))
    with (
        patch.object(cli, "RH56Driver", return_value=hand),
        patch.object(hand, "read_angle", return_value=ACTUAL_OPEN),
    ):
        code = cli.main(["finger", "index", "976", "--mock", "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert json.loads(captured.out)["data"]["target"] == [None, None, None, 976, None, None]
    assert hand.last_command["addr"] == REG_ANGLE_SET + 3 * 2
    assert hand.last_command["data"] == [976]


def test_unknown_status_is_visible_in_human_output(capsys):
    hand = RH56Driver.mock()
    with (
        patch.object(cli, "RH56Driver", return_value=hand),
        patch.object(hand, "read_status", return_value=[255] * 6),
    ):
        assert cli.main(["doctor", "--mock"]) == 0
    assert "WARN status:" in capsys.readouterr().out


def test_mock_diagnostics_do_not_verify_physical_health(capsys):
    assert cli.main(["doctor", "--mock", "--json"]) == 0
    assert not json.loads(capsys.readouterr().out)["data"]["health_verified"]


def test_state_marks_unknown_status_without_discarding_raw_feedback(capsys):
    hand = RH56Driver.mock()
    status = [255, 255, 255, 0, 255, 255]
    with (
        patch.object(cli, "RH56Driver", return_value=hand),
        patch.object(hand, "read_status", return_value=status),
    ):
        assert cli.main(["state", "--mock", "--fields", "status", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["status"] == status
    assert data["status_known"] == [False, False, False, True, False, False]


def test_known_fault_is_not_hidden_by_an_unknown_status(capsys):
    hand = RH56Driver.mock()
    with (
        patch.object(cli, "RH56Driver", return_value=hand),
        patch.object(hand, "read_status", return_value=[255, 6, 255, 255, 255, 255]),
    ):
        assert cli.main(["doctor", "--mock", "--json"]) == 5
    report = json.loads(capsys.readouterr().out)
    check = next(check for check in report["data"]["checks"] if check["name"] == "status")
    assert check["ok"] is False and check["severity"] == "error"
    assert not report["ok"] and not report["data"]["health_verified"]


def test_single_channel_wait_ignores_other_channels_position_limits():
    target = [None, None, None, 976, None, None]
    with RH56Driver.mock() as hand:
        actual = [997, 999, 996, 976, 1000, 886]
        with patch.object(hand, "read_angle", return_value=actual):
            assert hand.wait_until_reached(target, tolerance=1) == actual


def test_single_channel_wait_requires_selected_channel_to_arrive():
    with (
        RH56Driver.mock() as hand,
        patch.object(hand, "read_angle", return_value=ACTUAL_OPEN),
        pytest.raises(RH56TimeoutError),
    ):
        hand.wait_until_reached(
            [None, None, None, 976, None, None],
            tolerance=1,
            timeout=0.002,
            interval=0.001,
        )


@pytest.mark.parametrize(
    "target",
    [
        None,
        [None] * 5,
        [None] * 6,
        [None, None, None, True, None, None],
        [None, None, None, float("nan"), None, None],
        [None, None, None, 1001, None, None],
    ],
)
def test_invalid_wait_mask_fails_before_hardware_reads(target):
    with RH56Driver.mock() as hand:
        with patch.object(hand, "read_status") as read, pytest.raises(RH56ValidationError):
            hand.wait_until_reached(target)
        read.assert_not_called()


def test_isolated_finger_write_updates_cache_only_after_ack():
    with RH56Driver.mock() as hand:
        before = hand.commanded_angle
        with (
            patch.object(
                RH56Protocol, "parse_write_ack", side_effect=RH56HardwareError("rejected")
            ),
            pytest.raises(RH56HardwareError),
        ):
            hand.move_finger(3, 976, base="hold")
        assert hand.commanded_angle == before


def test_isolated_finger_write_preserves_other_cached_targets():
    with RH56Driver.mock() as hand:
        before = hand.commanded_angle
        hand.move_finger(3, 976, base="hold")
        assert hand.commanded_angle == [value if i != 3 else 976 for i, value in enumerate(before)]


def test_isolated_finger_retains_fault_guard_and_wait_checks_all_faults():
    with RH56Driver.mock() as hand:
        with (
            patch.object(hand, "read_status", return_value=[6, 255, 255, 1, 255, 255]),
            pytest.raises(RH56HardwareError),
        ):
            hand.wait_until_reached([None, None, None, 976, None, None])
        with patch.object(hand._transport, "request") as request, pytest.raises(RH56HardwareError):
            hand.move_finger(3, 976, base="hold")
        request.assert_not_called()
