import argparse

from rh56_sdk import RH56Driver


def main() -> None:
    parser = argparse.ArgumentParser(description="Set RH56 force threshold.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--force", type=int, default=300)
    parser.add_argument("--yes", action="store_true", help="Required to write hardware")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to write hardware without --yes")

    with RH56Driver(args.port, baud=args.baud) as hand:
        hand.set_force_threshold([args.force] * 6)
        print(f"force threshold set to {args.force}")


if __name__ == "__main__":
    main()
