import argparse
import csv
import json
from pathlib import Path

from rh56_sdk import RH56Driver
from rh56_sdk.diagnostics import RH56Diagnostics


def _parse_int_list(text: str):
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Characterize ANGLE_SET -> ANGLE_ACT tracking.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--speed", type=int, default=250)
    parser.add_argument("--fingers", default="3")
    parser.add_argument("--points", default="1000,800,600,800,1000")
    parser.add_argument("--tolerance", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--json", default="rh56_angle_tracking_report.json")
    parser.add_argument("--csv", default="rh56_angle_tracking_report.csv")
    parser.add_argument("--yes", action="store_true", help="Required: the hand will move")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to move hardware without --yes")

    fingers = _parse_int_list(args.fingers)
    points = _parse_int_list(args.points)

    with RH56Driver(args.port, baud=args.baud) as hand:
        report = RH56Diagnostics(hand).characterize_angle_tracking(
            points=points,
            fingers=fingers,
            tolerance=args.tolerance,
            timeout=args.timeout,
            speed=args.speed,
            require_confirm=False,
        )

    Path(args.json).write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with open(args.csv, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "finger",
                "target",
                "actual",
                "error",
                "reached",
                "time_to_reach",
                "status",
                "hardware_error",
            ],
        )
        writer.writeheader()
        for finger, rows in report["fingers"].items():
            for row in rows:
                writer.writerow({"finger": finger, **row})

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
