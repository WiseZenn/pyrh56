import argparse
import time


from rh56_sdk import RH56Driver


def main() -> None:
    parser = argparse.ArgumentParser(description="Open and close RH56 once.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--yes", action="store_true", help="Required to move hardware")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to move hardware without --yes")

    with RH56Driver(args.port, baud=args.baud) as hand:
        hand.set_speed([250] * 6)
        hand.open()
        time.sleep(5.0)
        hand.close()
        time.sleep(5.0)
        hand.open()


if __name__ == "__main__":
    main()
