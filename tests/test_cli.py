"""CLI integration tests use the SDK mock or injected faults, never physical ports."""

import json
from unittest.mock import patch

import pytest

from rh56_sdk import RH56Driver, SerialPortInfo
from rh56_sdk import cli
from rh56_sdk.constants import RH56_OPEN_FRAME
from rh56_sdk.exceptions import RH56ConnectionError, RH56TimeoutError
from rh56_sdk.transport import SerialTransport


@pytest.mark.parametrize(
    "command",
    [
        ["ping"],
        ["state"],
        ["doctor"],
        ["open"],
        ["close"],
        ["stop"],
        ["move", "--angles", "1000", "1000", "1000", "1000", "700", "900"],
        ["speed", "100", "100", "100", "100", "100", "100"],
        ["force", "100", "100", "100", "100", "100", "100"],
        ["clear-error"],
        ["calibrate", "validate", "--samples", "1"],
        ["calibrate", "baseline", "--confirm", "--samples", "1"],
    ],
)
def test_mock_commands_return_structured_success(capsys, command):
    assert cli.main(["--mock", *command, "--json"]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["schema_version"] == 1
    assert result["mock"] and result["ok"]
    assert result["command"] == command[0]
    assert captured.err == ""


def test_common_options_work_on_both_sides_of_command(capsys):
    assert cli.main(["--mock", "--id", "7", "state", "--json", "--fields", "angle"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["node_id"] == 7
    assert result["data"] == {"angle": [0] * 6}


@pytest.mark.parametrize(
    "option, thumb", [([], 1000), (["--conservative-limits"], 700), (["--factory-limits"], 1000)]
)
def test_cli_open_selects_default_or_conservative_preset(capsys, option, thumb):
    assert cli.main(["--mock", *option, "open", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["target"][4] == thumb


@pytest.mark.parametrize("option, expected", [([], 0), (["--conservative-limits"], 2)])
def test_cli_thumb_accepts_1000_by_default(capsys, option, expected):
    assert cli.main(["--mock", "finger", "thumb_flex", "1000", *option, "--json"]) == expected
    captured = capsys.readouterr()
    if expected == 0:
        assert json.loads(captured.out)["data"]["target"][4] == 1000
    else:
        assert captured.out == "" and json.loads(captured.err)["error"]["exit_code"] == 2


@pytest.mark.parametrize(
    "option, thumb", [([], 0), (["--conservative-limits"], 200), (["--factory-limits"], 200)]
)
def test_cli_close_selects_configured_lower_limit(capsys, option, thumb):
    assert cli.main(["--mock", "close", *option, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["target"][4] == thumb


def test_ports_enumerates_adapters_without_opening_any_device(capsys):
    adapter = SerialPortInfo("COM9", "USB RS485", "USB VID:PID=1234:5678", 0x1234, 0x5678)
    with patch.object(SerialTransport, "list_port_info", return_value=[adapter]):
        with patch.object(cli, "RH56Driver") as driver:
            assert cli.main(["ports", "--json"]) == 0
    driver.assert_not_called()
    assert json.loads(capsys.readouterr().out)["data"]["ports"][0]["device"] == "COM9"


def test_json_adapter_names_are_portable_across_windows_pipe_encodings(capsys):
    description = "因时串口适配器 🙂"
    adapter = SerialPortInfo("COM9", description, "USB")
    with patch.object(SerialTransport, "list_port_info", return_value=[adapter]):
        assert cli.main(["ports", "--json"]) == 0
    output = capsys.readouterr().out
    # Simulate legacy Windows pipe encoding followed by a UTF-8 JSON consumer.
    decoded = output.encode("gbk").decode("utf-8")
    assert json.loads(decoded)["data"]["ports"][0]["description"] == description


def test_json_errors_are_portable_across_windows_pipe_encodings(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "connect", side_effect=RH56ConnectionError("串口被占用 🙂")):
            assert cli.main(["ping", "--mock", "--json"]) == 3
    output = capsys.readouterr().err
    assert json.loads(output.encode("gbk").decode("utf-8"))["error"]["message"] == "串口被占用 🙂"


@pytest.mark.parametrize(
    "tokens",
    [
        ["state"],
        ["--mock", "--port", "COM3", "state"],
        ["--mock", "--factory-limits", "--conservative-limits", "state"],
        ["--mock", "--factory-limits", "state", "--conservative-limits"],
        ["--mock", "--id", "0", "ping"],
        ["--mock", "--timeout", "nan", "state"],
        ["--mock", "--timeout", "-1", "state"],
        ["--mock", "state", "--fields", "invalid"],
        ["--mock", "state", "--jsonl"],
        ["--mock", "watch", "--json"],
        ["--mock", "watch", "--interval", "0"],
        ["--mock", "watch", "--count", "-1"],
        ["--mock", "open", "--tolerance", "1001"],
        ["--mock", "move", "--angles", "0", "0", "0", "0", "-1", "0"],
        ["--mock", "finger", "thumb_flex", "-1"],
        ["--mock", "calibrate", "force"],
        ["--mock", "calibrate", "force", "--confirm", "--wait-seconds", "1"],
        ["--mock", "calibrate", "baseline"],
        ["--mock", "calibrate", "validate", "--samples", "0"],
        ["--mock", "speed", "-1", "0", "0", "0", "0", "0"],
        ["unknown-command"],
    ],
)
def test_invalid_cli_arguments_fail_before_device_construction(capsys, tokens):
    with patch.object(cli, "RH56Driver") as driver:
        assert cli.main([*tokens, "--json"]) == 2
    driver.assert_not_called()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["exit_code"] == 2


def test_watch_has_exact_count_and_jsonl_records(capsys):
    assert cli.main(["watch", "--mock", "--count", "3", "--interval", "0.001", "--jsonl"]) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["sequence"] for record in records] == [1, 2, 3]


def test_watch_retains_valid_records_when_later_read_fails(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "read_angle", side_effect=[[0] * 6, RH56TimeoutError("unplugged")]):
            assert (
                cli.main(
                    [
                        "watch",
                        "--mock",
                        "--count",
                        "2",
                        "--interval",
                        "0.001",
                        "--fields",
                        "angle",
                        "--jsonl",
                    ]
                )
                == 4
            )
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.err)["error"]["type"] == "RH56TimeoutError"
    assert not hand.is_connected


def test_motion_preflight_fault_blocks_all_writes(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "read_error", return_value=[1, 0, 0, 0, 0, 0]):
            with patch.object(hand, "move_to") as move:
                with patch.object(hand, "stop_motion") as stop:
                    assert cli.main(["open", "--mock", "--json"]) == 5
    move.assert_not_called()
    stop.assert_not_called()
    assert capsys.readouterr().out == ""


def test_invalid_finger_target_does_not_write_or_stop(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "stop_motion") as stop:
            assert cli.main(["finger", "index", "1001", "--mock", "--json"]) == 2
    stop.assert_not_called()
    assert hand.last_command is None
    assert json.loads(capsys.readouterr().err)["error"]["exit_code"] == 2


def test_stop_does_not_depend_on_angle_reads(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(
            hand, "read_angle", side_effect=RH56TimeoutError("angle unavailable")
        ) as read:
            assert cli.main(["stop", "--mock", "--json"]) == 0
    read.assert_not_called()
    assert json.loads(capsys.readouterr().out)["data"]["acknowledged"]


def test_mock_wait_does_not_claim_simulated_motion(capsys):
    assert (
        cli.main(
            [
                "open",
                "--mock",
                "--wait",
                "--wait-timeout",
                "0.002",
                "--poll-interval",
                "0.001",
                "--json",
            ]
        )
        == 4
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    result = json.loads(captured.err)
    assert result["recovery"]["zero_speed_acknowledged"]
    assert not result["recovery"]["hardware_stop_verified"]


def test_wait_reports_reached_only_after_actual_feedback(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "read_angle", return_value=RH56_OPEN_FRAME):
            assert cli.main(["open", "--mock", "--wait", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["reached"] is True and data["actual"] == RH56_OPEN_FRAME


def test_motion_interrupt_attempts_stop_before_disconnect(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "wait_until_reached", side_effect=KeyboardInterrupt):
            with patch.object(hand, "stop_motion", wraps=hand.stop_motion) as stop:
                assert cli.main(["open", "--mock", "--wait", "--json"]) == 130
    stop.assert_called_once()
    assert not hand.is_connected
    assert json.loads(capsys.readouterr().err)["recovery"]["zero_speed_acknowledged"]


def test_read_only_interrupt_never_writes_a_stop(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "read_angle", side_effect=KeyboardInterrupt):
            with patch.object(hand, "stop_motion") as stop:
                assert cli.main(["watch", "--mock", "--jsonl"]) == 130
    stop.assert_not_called()
    assert json.loads(capsys.readouterr().err)["error"]["exit_code"] == 130


def test_failed_stop_preserves_original_motion_error(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "move_to", side_effect=RH56TimeoutError("no ACK")):
            with patch.object(hand, "stop_motion", side_effect=RH56ConnectionError("disconnected")):
                assert cli.main(["open", "--mock", "--json"]) == 4
    result = json.loads(capsys.readouterr().err)
    assert result["error"]["message"] == "no ACK"
    assert not result["recovery"]["zero_speed_acknowledged"]


def test_connection_error_is_structured_and_does_not_claim_device_response(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "connect", side_effect=RH56ConnectionError("port busy")):
            assert cli.main(["ping", "--mock", "--json"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["exit_code"] == 3


def test_doctor_explicit_mock_port_does_not_verify_physical_health(capsys):
    assert cli.main(["doctor", "--port", "COM_MOCK", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mock"] is True and result["data"]["health_verified"] is False


def test_doctor_connection_failure_reports_unverified_health(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "connect", side_effect=RH56ConnectionError("port busy")):
            assert cli.main(["doctor", "--mock", "--json"]) == 3
    report = json.loads(capsys.readouterr().out)
    assert not report["ok"] and report["data"]["health_verified"] is False


def test_doctor_continues_after_a_failed_field_and_reports_faults(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "read_angle", side_effect=RH56TimeoutError("no angle")):
            with patch.object(hand, "read_error", return_value=[1, 0, 0, 0, 0, 0]):
                assert cli.main(["doctor", "--mock", "--json"]) == 5
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"]
    checks = {check["name"]: check for check in result["data"]["checks"]}
    assert not checks["angle"]["ok"] and not checks["error"]["ok"]
    assert checks["voltage"]["ok"]


def test_finger_only_writes_selected_register_without_angle_reads(capsys):
    hand = RH56Driver.mock()
    with patch.object(cli, "RH56Driver", return_value=hand):
        with patch.object(hand, "read_angle", side_effect=RH56TimeoutError("unavailable")) as read:
            assert cli.main(["finger", "index", "800", "--mock", "--json"]) == 0
    read.assert_not_called()
    assert json.loads(capsys.readouterr().out)["data"]["target"] == [
        None,
        None,
        None,
        800,
        None,
        None,
    ]
    assert hand.last_command["data"] == [800]


def test_baseline_profile_round_trip_cli(tmp_path, capsys):
    profile = str(tmp_path / "baseline.json")
    assert (
        cli.main(
            [
                "calibrate",
                "baseline",
                "--mock",
                "--confirm",
                "--samples",
                "1",
                "--profile",
                profile,
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        cli.main(
            ["calibrate", "validate", "--mock", "--samples", "1", "--profile", profile, "--json"]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["data"]["uses_offset"]


def test_hardware_calibration_calls_existing_sdk(capsys):
    with patch.object(cli.ForceCalibration, "run_official", return_value=True) as calibrate:
        assert cli.main(["calibrate", "force", "--mock", "--confirm", "--json"]) == 0
    calibrate.assert_called_once_with(timeout=8.0, require_confirm=False)
    result = json.loads(capsys.readouterr().out)["data"]
    assert result["fault_check_passed"]
    assert result["zero_validated"] is False
