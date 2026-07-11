import argparse


from rh56_sdk import RH56Driver


def main() -> None:
    parser = argparse.ArgumentParser(description="Open and close an RH56 connection.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    hand = RH56Driver(args.port, baud=args.baud)
    hand.connect()
    try:
        print(f"connected={hand.is_connected}")
    finally:
        hand.disconnect()
        print(f"connected={hand.is_connected}")


if __name__ == "__main__":
    main()
