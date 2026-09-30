import argparse
import json
from pathlib import Path

from rh56_grasp import BenchmarkLogger, GraspController, PressureCloseConfig
from rh56_sdk import RH56Driver


def main() -> None:
    parser = argparse.ArgumentParser(description="RH56 high-level pressure grasp demo.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--grasp", default="pinch")
    parser.add_argument("--speed", type=int, default=200)
    parser.add_argument("--force-threshold", type=int, default=80)
    parser.add_argument("--step", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--hold-time", type=float, default=1.0)
    parser.add_argument("--target-tolerance", type=int, default=30)
    parser.add_argument("--pre-shape-timeout", type=float, default=3.0)
    parser.add_argument("--pre-shape-tolerance", type=int, default=30)
    parser.add_argument(
        "--contact-direction",
        choices=("positive", "negative", "absolute"),
        default="positive",
    )
    parser.add_argument("--force-zero-offset", default="rh56_force_zero_offset.json")
    parser.add_argument("--object-name", default="")
    parser.add_argument("--object-size", default="")
    parser.add_argument("--object-weight", default="")
    parser.add_argument("--object-material", default="")
    parser.add_argument("--log", default="rh56_grasp_trials.csv")
    parser.add_argument("--yes", action="store_true", help="Required: the hand will move")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to run pressure grasp without --yes")

    config = PressureCloseConfig(
        force_threshold=args.force_threshold,
        step=args.step,
        timeout=args.timeout,
        hold_time=args.hold_time,
        target_tolerance=args.target_tolerance,
        contact_direction=args.contact_direction,
    )
    with RH56Driver(args.port, baud=args.baud) as hand:
        offset_path = Path(args.force_zero_offset)
        if offset_path.exists():
            data = json.loads(offset_path.read_text(encoding="utf-8"))
            hand.force_zero_offset = [int(v) for v in data["force_zero_offset"]]
            print(f"Loaded force_zero_offset: {hand.force_zero_offset}")

        controller = GraspController(
            hand,
            logger=BenchmarkLogger(args.log),
            default_speed=args.speed,
            pre_shape_timeout=args.pre_shape_timeout,
            pre_shape_tolerance=args.pre_shape_tolerance,
        )
        trial = controller.grasp(
            args.grasp,
            force_threshold=args.force_threshold,
            speed=args.speed,
            object_name=args.object_name,
            object_size=args.object_size,
            object_weight=args.object_weight,
            object_material=args.object_material,
            config=config,
        )
        print(trial.pressure_result)


if __name__ == "__main__":
    main()
