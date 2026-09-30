import argparse

from rh56_sdk import RH56Driver


def main() -> None:
    parser = argparse.ArgumentParser(description="Read one RH56 state snapshot.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    with RH56Driver(args.port, baud=args.baud) as hand:
        print("angle:", hand.read_angle())
        print("force:", hand.read_force())
        print("status:", hand.read_status())
        print("error:", hand.read_error())


if __name__ == "__main__":
    main()
