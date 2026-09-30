import argparse
import json
import time
from pathlib import Path

from rh56_sdk import RH56Driver
from rh56_sdk.calibration import ForceCalibration
from rh56_sdk.diagnostics import RH56Diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger official RH56 force-sensor calibration.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--tolerance", type=int, default=30)
    parser.add_argument("--output", default="rh56_force_calibration_report.json")
    parser.add_argument("--yes", action="store_true", help="Required: the hand will move")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit(
            "Refusing to start official force calibration without --yes. "
            "The hand will move automatically for about 6 seconds and must be unloaded."
        )

    with RH56Driver(args.port, baud=args.baud) as hand:
        calibration = ForceCalibration(hand)
        diagnostics = RH56Diagnostics(hand)
        before = diagnostics.read_calibration_snapshot()
        started_at = time.time()
        calibration.run_official(
            wait=True,
            timeout=args.timeout,
            require_confirm=False,
        )
        after = diagnostics.read_calibration_snapshot()
        zero = calibration.validate_baseline(
            samples=args.samples,
            tolerance=args.tolerance,
        )

    report = {
        "started_at": started_at,
        "timeout": args.timeout,
        "before": before,
        "after": after,
        "force_zero_validation": zero,
    }
    Path(args.output).write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
