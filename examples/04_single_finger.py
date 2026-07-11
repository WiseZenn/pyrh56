import argparse
import time


from rh56_sdk import RH56Driver
from rh56_sdk.constants import RH56_OPEN_FRAME


def main() -> None:
    parser = argparse.ArgumentParser(description="Move one RH56 finger slowly.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--finger", type=int, default=3)
    parser.add_argument("--target", type=int, default=700)
    parser.add_argument("--yes", action="store_true", help="Required to move hardware")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to move hardware without --yes")

    with RH56Driver(args.port, baud=args.baud) as hand:
        hand.set_speed([250] * 6)
        hand.move_to(RH56_OPEN_FRAME)
        time.sleep(0.5)
        hand.move_finger(args.finger, args.target)
        time.sleep(1.0)
        print("angle:", hand.read_angle())
        hand.move_to(RH56_OPEN_FRAME)


if __name__ == "__main__":
    main()
