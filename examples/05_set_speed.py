import argparse


from rh56_sdk import RH56Driver


def main() -> None:
    parser = argparse.ArgumentParser(description="Set RH56 servo speed.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--speed", type=int, default=250)
    parser.add_argument("--yes", action="store_true", help="Required to write hardware")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to write hardware without --yes")

    with RH56Driver(args.port, baud=args.baud) as hand:
        hand.set_speed([args.speed] * 6)
        print(f"speed set to {args.speed}")


if __name__ == "__main__":
    main()
