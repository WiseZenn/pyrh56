"""Terminal commands for the pyrh56 SDK, with no additional runtime dependencies."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any, NoReturn

from . import __version__
from .calibration import ForceCalibration
from .configuration import CONSERVATIVE_LIMITS, DEFAULT_LIMITS, FACTORY_LIMITS, RH56Config
from .driver import RH56Driver
from .enums import Finger
from .exceptions import (
    RH56ConnectionError,
    RH56Error,
    RH56HardwareError,
    RH56ProtocolError,
    RH56SafetyError,
    RH56TimeoutError,
    RH56ValidationError,
)
from .registers import STATUS_TEXT
from .safety import (
    make_safe_close_frame,
    make_safe_open_frame,
    normalize_angle_command,
    normalize_u16_vector,
)
from .transport import SerialTransport

CHANNELS = tuple(finger.name.lower() for finger in Finger)
FIELDS = ("angle", "force", "status", "error", "current", "temperature", "voltage")
MOTION_COMMANDS = {"move", "finger", "open", "close"}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise RH56ValidationError(message)


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("expected a finite number > 0")
    return value


def _nonnegative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("expected an integer >= 0")
    return value


def _fields(text: str) -> list[str]:
    selected = text.split(",")
    if not selected or any(field not in FIELDS for field in selected):
        raise argparse.ArgumentTypeError(f"fields must be comma-separated names from {FIELDS}")
    if len(set(selected)) != len(selected):
        raise argparse.ArgumentTypeError("duplicate fields are not allowed")
    return selected


def _common(parser: argparse.ArgumentParser, *, suppress: bool) -> None:
    def default(value: Any) -> Any:
        return argparse.SUPPRESS if suppress else value

    parser.add_argument(
        "--port", default=default(None), help="serial port, e.g. COM3 or /dev/ttyUSB0"
    )
    parser.add_argument(
        "--mock", action="store_true", default=default(False), help="zero-feedback mock"
    )
    parser.add_argument(
        "--baud", type=int, default=default(115200), help="115200 (default), 57600, or 19200"
    )
    parser.add_argument(
        "--id", dest="node_id", type=int, default=default(1), help="hand ID, 1-254 (1)"
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=default(0.1),
        help="per-request timeout in seconds",
    )
    limit_options = parser.add_mutually_exclusive_group()
    limit_options.add_argument(
        "--factory-limits",
        action="store_true",
        default=default(False),
        help="compatibility profile: thumb range 200-1000 (default is 0-1000)",
    )
    limit_options.add_argument(
        "--conservative-limits",
        action="store_true",
        default=default(False),
        help="limit thumb flex to 200-700 instead of the default 0-1000",
    )
    parser.add_argument(
        "--json", action="store_true", default=default(False), help="structured JSON"
    )
    parser.add_argument(
        "--jsonl",
        action="store_true",
        default=default(False),
        help="stream JSON lines (watch only)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser. Common options work before or after the command."""
    parser = _Parser(
        prog="pyrh56",
        allow_abbrev=False,
        description="Independent Python tools for the RH56 private serial protocol.",
        epilog="Channel order: "
        + ", ".join(CHANNELS)
        + ". Angle values are device units, not degrees.",
    )
    _common(parser, suppress=False)
    parser.add_argument("--version", action="version", version=f"pyrh56 {__version__}")
    common = _Parser(add_help=False, allow_abbrev=False)
    _common(common, suppress=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        return subparsers.add_parser(name, help=help_text, parents=[common], allow_abbrev=False)

    command("ports", "list serial adapters without opening them")
    command("ping", "verify a protocol response by reading angle feedback")
    state = command("state", "read a feedback snapshot")
    state.add_argument("--fields", type=_fields, default=list(FIELDS))
    watch = command("watch", "poll feedback until interrupted or count is reached")
    watch.add_argument("--fields", type=_fields, default=["angle", "force", "status", "error"])
    watch.add_argument(
        "--interval", type=_positive_float, default=0.1, help="delay between snapshots"
    )
    watch.add_argument(
        "--count", type=_nonnegative_int, default=0, help="snapshot count; 0 is unlimited"
    )
    command("doctor", "read-only communication and hardware checks with suggestions")

    for name, help_text in (
        ("move", "write six target angle values"),
        ("finger", "write one channel register, leaving other channels untouched"),
        ("open", "send the SDK open preset"),
        ("close", "send the SDK close preset"),
    ):
        motion = command(name, help_text)
        if name == "move":
            motion.add_argument("--angles", nargs=6, type=int, required=True, metavar="N")
        elif name == "finger":
            motion.add_argument("channel", choices=CHANNELS)
            motion.add_argument("value", type=int)
        motion.add_argument(
            "--wait", action="store_true", help="wait for angle feedback to reach target"
        )
        motion.add_argument("--wait-timeout", type=_positive_float, default=5.0)
        motion.add_argument(
            "--tolerance", type=_nonnegative_int, default=20, help="device angle units"
        )
        motion.add_argument("--poll-interval", type=_positive_float, default=0.05)

    command(
        "stop", "request zero speed and verify ACK; stopping behavior needs hardware validation"
    )
    for name, help_text in (
        ("speed", "set six speed values (0-1000)"),
        ("force", "set six force thresholds (0-1000)"),
    ):
        setting = command(name, help_text)
        setting.add_argument("values", nargs=6, type=int, metavar="N")
    command("clear-error", "clear faults and verify STATUS/ERROR again")
    calibration = command("calibrate", "hardware force calibration or software baseline sampling")
    calibration.add_argument("mode", choices=("force", "baseline", "validate"))
    calibration.add_argument("--confirm", action="store_true", help="confirm an unloaded hand")
    calibration.add_argument("--wait-seconds", type=_positive_float, default=8.0)
    calibration.add_argument("--samples", type=int, default=50)
    calibration.add_argument("--interval", type=_positive_float, default=0.02)
    calibration.add_argument("--tolerance", type=_nonnegative_int, default=30)
    calibration.add_argument(
        "--profile", help="baseline JSON to save (baseline) or load (validate)"
    )
    return parser


def _validate_arguments(args: argparse.Namespace) -> RH56Config | None:
    if args.json and args.jsonl:
        raise RH56ValidationError("choose either --json or --jsonl")
    if args.jsonl and args.command != "watch":
        raise RH56ValidationError("--jsonl is available only for watch")
    if args.json and args.command == "watch":
        raise RH56ValidationError("use --jsonl for watch")
    if args.mock and args.port is not None:
        raise RH56ValidationError("choose either --mock or --port")
    if args.factory_limits and args.conservative_limits:
        raise RH56ValidationError("choose either --factory-limits or --conservative-limits")
    if args.command == "ports":
        if args.mock or args.port is not None:
            raise RH56ValidationError("ports enumerates real adapters; omit --port and --mock")
        return None
    if not args.mock and args.port is None:
        raise RH56ValidationError("specify --port (e.g. --port COM3) or explicitly select --mock")
    config = RH56Config(
        port="COM_MOCK" if args.mock else args.port,
        baud=args.baud,
        node_id=args.node_id,
        timeout=args.timeout,
        limits=(
            CONSERVATIVE_LIMITS
            if args.conservative_limits
            else (FACTORY_LIMITS if args.factory_limits else DEFAULT_LIMITS)
        ),
    )
    if args.command in MOTION_COMMANDS:
        if args.tolerance > 1000:
            raise RH56ValidationError("tolerance must be in [0, 1000]")
        if args.command == "move":
            normalize_angle_command(args.angles, config.limits)
        elif args.command == "finger":
            channel = CHANNELS.index(args.channel)
            limit = config.limits.as_tuple()[channel]
            normalize_u16_vector(
                [args.value],
                name=args.channel,
                count=1,
                minimum=limit.minimum,
                maximum=limit.maximum,
            )
        else:
            normalize_angle_command(
                make_safe_open_frame(config.limits)
                if args.command == "open"
                else make_safe_close_frame(config.limits),
                config.limits,
            )
    elif args.command in {"speed", "force"}:
        normalize_u16_vector(args.values, name=args.command)
    elif args.command == "calibrate":
        if args.mode in {"force", "baseline"} and not args.confirm:
            raise RH56ValidationError("confirm the hand is unloaded by passing --confirm")
        if args.mode == "force" and args.wait_seconds < 6:
            raise RH56ValidationError("hardware calibration wait must be >= 6 seconds")
        if args.mode == "force" and args.profile:
            raise RH56ValidationError("--profile is used with baseline or validate")
        if args.samples < 1 or args.tolerance > 32767:
            raise RH56ValidationError("samples must be >= 1 and tolerance must be in [0, 32767]")
    return config


def _snapshot(hand: RH56Driver, fields: Sequence[str]) -> dict[str, object]:
    readers = {
        "angle": hand.read_angle,
        "force": hand.read_force,
        "status": hand.read_status,
        "error": hand.read_error,
        "current": hand.read_current,
        "temperature": hand.read_temperature,
        "voltage": hand.read_voltage,
    }
    data: dict[str, object] = {field: readers[field]() for field in fields}
    if "status" in fields:
        status = data["status"]
        assert isinstance(status, list)
        data["status_text"] = [hand.decode_status(value)[1] for value in status]
        data["status_known"] = [value in STATUS_TEXT for value in status]
    if "error" in fields:
        errors = data["error"]
        assert isinstance(errors, list)
        data["error_text"] = [hand.decode_error(value) for value in errors]
    return data


def _emit(
    args: argparse.Namespace,
    data: dict[str, object],
    *,
    ok: bool = True,
    sequence: int | None = None,
) -> None:
    record = {
        "schema_version": 1,
        "command": args.command,
        "ok": ok,
        "timestamp": time.time(),
        "mock": bool(args.mock or args.port == "COM_MOCK"),
        "port": "COM_MOCK" if args.mock else args.port,
        "node_id": args.node_id,
        "data": data,
    }
    if sequence is not None:
        record["sequence"] = sequence
    if args.json or args.jsonl:
        # ASCII escapes are valid UTF-8 even when a Windows pipe uses a legacy code page.
        print(json.dumps(record, ensure_ascii=True, allow_nan=False), flush=True)
        return
    if args.mock or args.port == "COM_MOCK":
        print("MOCK: zero feedback; no physical device or motion simulation.")
    if sequence is not None:
        print(f"Snapshot {sequence}")
    if args.command in {"state", "watch"}:
        print("Channels: " + ", ".join(CHANNELS))
    for key, value in data.items():
        if key == "ports" and isinstance(value, list):
            if not value:
                print("No serial adapters found.")
            for port in value:
                print(f"{port['device']}: {port['description']} ({port['hwid']})")
        elif key == "checks" and isinstance(value, list):
            for check in value:
                label = (
                    "WARN"
                    if check.get("severity") == "warning"
                    else ("PASS" if check["ok"] else "FAIL")
                )
                print(f"{label} {check['name']}: {check['detail']}")
                if check.get("hint"):
                    print(f"  {check['hint']}")
        else:
            print(f"{key}: {json.dumps(value, ensure_ascii=False)}")


def _doctor(hand: RH56Driver, args: argparse.Namespace) -> int:
    checks: list[dict[str, object]] = []
    try:
        hand.connect(verify=False)
    except RH56Error as exc:
        checks.append({"name": "serial", "ok": False, "detail": str(exc), "hint": _hint(exc)})
        _emit(args, {"checks": checks, "health_verified": False}, ok=False)
        return _exit_code(exc)
    checks.append({"name": "serial", "ok": True, "detail": "serial port opened"})
    readers = {
        "angle": hand.read_angle,
        "status": hand.read_status,
        "error": hand.read_error,
        "force": hand.read_force,
        "current": hand.read_current,
        "temperature": hand.read_temperature,
        "voltage": hand.read_voltage,
    }
    exit_code = 0
    health_verified = not (args.mock or args.port == "COM_MOCK")
    for name, read in readers.items():
        try:
            values = read()
        except RH56Error as exc:
            exit_code = max(exit_code, _exit_code(exc))
            health_verified = False
            checks.append({"name": name, "ok": False, "detail": str(exc), "hint": _hint(exc)})
            continue
        fault = isinstance(values, list) and (
            (name == "error" and any(values))
            or (name == "status" and any(value in {5, 6, 7} for value in values))
        )
        unknown = (
            name == "status"
            and isinstance(values, list)
            and any(value not in STATUS_TEXT for value in values)
        )
        if unknown:
            health_verified = False
        hint = None
        if fault:
            hint = "Inspect the device fault before using clear-error."
        elif unknown:
            hint = (
                "Unrecognized status codes: health is unverified. Check the model/firmware manual."
            )
        checks.append(
            {
                "name": name,
                "ok": False if fault else (None if unknown else True),
                "detail": values,
                "hint": hint,
                "severity": "error" if fault else ("warning" if unknown else "info"),
            }
        )
        if fault:
            exit_code = 5
            health_verified = False
    _emit(args, {"checks": checks, "health_verified": health_verified}, ok=exit_code == 0)
    return exit_code


def _execute(hand: RH56Driver, args: argparse.Namespace) -> int:
    if args.command == "ping":
        _emit(args, {"responding": True, "angle": hand.read_angle(), "baud": args.baud})
    elif args.command == "state":
        _emit(args, _snapshot(hand, args.fields))
    elif args.command == "watch":
        count = 0
        while args.count == 0 or count < args.count:
            data = _snapshot(hand, args.fields)
            count += 1
            _emit(args, data, sequence=count)
            if args.count == 0 or count < args.count:
                time.sleep(args.interval)
    elif args.command in MOTION_COMMANDS:
        return _motion(hand, args)
    elif args.command == "stop":
        hand.stop_motion()
        _emit(
            args,
            {
                "acknowledged": True,
                "speed": [0] * 6,
                "note": "Zero-speed write acknowledged; hardware stopping behavior is unverified. "
                "Set speed explicitly before subsequent motion.",
            },
        )
    elif args.command in {"speed", "force"}:
        hand.check_motion_ready()
        if args.command == "speed":
            hand.set_speed(args.values)
        else:
            hand.set_force_threshold(args.values)
        _emit(args, {"acknowledged": True, args.command: args.values})
    elif args.command == "clear-error":
        hand.clear_error()
        _emit(args, {"cleared": True})
    elif args.command == "calibrate":
        calibration = ForceCalibration(hand)
        if args.mode == "force":
            hand.check_motion_ready()
            try:
                calibration.run_official(timeout=args.wait_seconds, require_confirm=False)
            except (RH56Error, KeyboardInterrupt) as exc:
                return _report_error(
                    exc, structured=args.json, command=args.command, recovery=_try_stop(hand)
                )
            _emit(
                args,
                {
                    "mode": args.mode,
                    "waited_seconds": args.wait_seconds,
                    "fault_check_passed": True,
                    "zero_validated": False,
                },
            )
        elif args.mode == "baseline":
            offset = calibration.measure_baseline(samples=args.samples, interval=args.interval)
            if args.profile:
                calibration.save_profile(args.profile)
            _emit(args, {"mode": args.mode, "force_zero_offset": offset, "profile": args.profile})
        else:
            if args.profile:
                calibration.load_profile(args.profile)
            result = calibration.validate_baseline(
                samples=args.samples,
                interval=args.interval,
                tolerance=args.tolerance,
                use_offset=bool(args.profile),
            )
            _emit(args, result, ok=bool(result["ok"]))
            return 0 if result["ok"] else 5
    return 0


def _motion(hand: RH56Driver, args: argparse.Namespace) -> int:
    hand.check_motion_ready()
    # A failed ACK may still mean the write reached the device. Attempt zero speed
    # on any failure after beginning the motion command, while the port is open.
    try:
        if args.command == "move":
            hand.move_to(args.angles)
        elif args.command == "finger":
            hand.move_finger(CHANNELS.index(args.channel), args.value, base="hold")
        elif args.command == "open":
            hand.open_hand()
        else:
            hand.close()
        target: list[int | None] = list(hand.commanded_angle)
        if args.command == "finger":
            channel = CHANNELS.index(args.channel)
            target = [value if i == channel else None for i, value in enumerate(target)]
        result: dict[str, object] = {"acknowledged": True, "target": target, "reached": None}
        if args.wait:
            result["actual"] = hand.wait_until_reached(
                target,
                timeout=args.wait_timeout,
                tolerance=args.tolerance,
                interval=args.poll_interval,
            )
            result["reached"] = True
        _emit(args, result)
        return 0
    except RH56ValidationError:
        # No angle write occurs when command normalization fails.
        raise
    except (RH56Error, KeyboardInterrupt) as exc:
        return _report_error(
            exc, structured=args.json, command=args.command, recovery=_try_stop(hand)
        )


def _try_stop(hand: RH56Driver) -> dict[str, object]:
    try:
        hand.stop_motion()
        return {"zero_speed_acknowledged": True, "hardware_stop_verified": False}
    except RH56Error as exc:
        return {
            "zero_speed_acknowledged": False,
            "hardware_stop_verified": False,
            "error": str(exc),
        }


def _exit_code(exc: BaseException) -> int:
    if isinstance(exc, RH56ValidationError):
        return 2
    if isinstance(exc, RH56ConnectionError):
        return 3
    if isinstance(exc, (RH56TimeoutError, RH56ProtocolError)):
        return 4
    if isinstance(exc, (RH56HardwareError, RH56SafetyError)):
        return 5
    return 1


def _hint(exc: BaseException) -> str:
    if isinstance(exc, RH56ConnectionError):
        return "Check the port, permissions, adapter driver, and other programs using the port."
    if isinstance(exc, (RH56TimeoutError, RH56ProtocolError)):
        return "Check device power, wiring, baud rate, and hand ID. For motion, inspect feedback."
    if isinstance(exc, RH56ValidationError):
        return "Run pyrh56 <command> --help for accepted arguments and limits."
    if isinstance(exc, (RH56HardwareError, RH56SafetyError)):
        return "Read state or doctor, inspect the hardware, then clear the fault if appropriate."
    return "Check the file path and error details."


def _report_error(
    exc: BaseException,
    *,
    structured: bool,
    command: str | None = None,
    recovery: dict[str, object] | None = None,
) -> int:
    code = 130 if isinstance(exc, KeyboardInterrupt) else _exit_code(exc)
    message = "Interrupted." if isinstance(exc, KeyboardInterrupt) else str(exc)
    if structured:
        record: dict[str, object] = {
            "schema_version": 1,
            "command": command,
            "ok": False,
            "error": {
                "type": type(exc).__name__,
                "message": message,
                "exit_code": code,
                "hint": None if code == 130 else _hint(exc),
            },
        }
        if recovery is not None:
            record["recovery"] = recovery
        print(json.dumps(record, ensure_ascii=True), file=sys.stderr)
    else:
        print(f"pyrh56: {message}", file=sys.stderr)
        if code != 130:
            print(_hint(exc), file=sys.stderr)
        if recovery is not None:
            print(f"Zero-speed recovery: {json.dumps(recovery)}", file=sys.stderr)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a stable process exit code."""
    tokens = list(sys.argv[1:] if argv is None else argv)
    structured = "--json" in tokens or "--jsonl" in tokens
    args: argparse.Namespace | None = None
    hand: RH56Driver | None = None
    try:
        args = build_parser().parse_args(tokens)
        config = _validate_arguments(args)
        if args.command == "ports":
            _emit(args, {"ports": [asdict(port) for port in SerialTransport.list_port_info()]})
            return 0
        assert config is not None
        hand = RH56Driver(config)
        try:
            if args.command == "doctor":
                return _doctor(hand, args)
            # In particular, stop must not depend on a successful angle synchronization.
            hand.connect(verify=False)
            return _execute(hand, args)
        finally:
            hand.disconnect()
    except BrokenPipeError:
        return 0
    except (RH56Error, OSError, KeyboardInterrupt) as exc:
        return _report_error(exc, structured=structured, command=args.command if args else None)


if __name__ == "__main__":
    raise SystemExit(main())
