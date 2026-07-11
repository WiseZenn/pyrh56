import argparse
import json


from rh56_sdk import RH56Driver
from rh56_sdk.calibration import ForceCalibration
from rh56_sdk.diagnostics import RH56Diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate unloaded FORCE_ACT zero and save software offset."
    )
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--interval", type=float, default=0.02)
    parser.add_argument("--tolerance", type=int, default=30)
    parser.add_argument("--output", default="rh56_force_zero_offset.json")
    args = parser.parse_args()

    with RH56Driver(args.port, baud=args.baud) as hand:
        calibration = ForceCalibration(hand)
        diagnostics = RH56Diagnostics(hand)
        offset = calibration.measure_baseline(
            samples=args.samples,
            interval=args.interval,
        )
        validation = calibration.validate_baseline(
            samples=args.samples,
            tolerance=args.tolerance,
            interval=args.interval,
        )
        snapshot = diagnostics.read_calibration_snapshot()

    report = {
        "force_zero_offset": offset,
        "validation": validation,
        "snapshot": snapshot,
    }
    calibration.save_profile(args.output, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
