import argparse
import csv
import time

from rh56_sdk import RH56Driver
from rh56_sdk.constants import RH56_OPEN_FRAME

FAULT_STATUS = {5, 6, 7}


def _stop_on_fault(hand: RH56Driver, status):
    if any(code in FAULT_STATUS for code in status):
        try:
            hand.stop_motion()
        finally:
            raise RuntimeError(f"Fault status reported, stopped speed: {status}")


def _wait_until_reached(hand, index, target, tolerance, timeout):
    start = time.monotonic()
    last = {}
    while time.monotonic() - start < timeout:
        angle = hand.read_angle()
        force = hand.read_force()
        status = hand.read_status()
        error = hand.read_error()
        _stop_on_fault(hand, status)

        actual = angle[index]
        last = {
            "angle": angle,
            "force": force,
            "status": status,
            "error": error,
            "actual": actual,
        }
        if abs(actual - target) <= tolerance:
            return True, time.monotonic() - start, last
        time.sleep(0.02)
    return False, time.monotonic() - start, last


def main() -> None:
    parser = argparse.ArgumentParser(description="Low-speed single-finger move and readback test.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--finger", type=int, default=3, help="0-5, default index finger")
    parser.add_argument("--speed", type=int, default=250)
    parser.add_argument("--tolerance", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--csv", default="rh56_move_and_readback.csv")
    args = parser.parse_args()

    sequence = [1000, 800, 600, 800, 1000]
    fields = [
        "timestamp",
        "finger",
        "target_angle",
        "actual_angle",
        "reached",
        "time_to_reach_s",
        "status",
        "force",
        "error",
    ]

    with RH56Driver(args.port, baud=args.baud) as hand:
        hand.set_speed([args.speed] * 6)
        hand.move_to(RH56_OPEN_FRAME)
        time.sleep(0.3)

        with open(args.csv, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()

            for target in sequence:
                hand.move_finger(args.finger, target)
                reached, elapsed, last = _wait_until_reached(
                    hand,
                    args.finger,
                    target,
                    args.tolerance,
                    args.timeout,
                )
                actual = last.get("actual", "")
                row = {
                    "timestamp": f"{time.time():.3f}",
                    "finger": args.finger,
                    "target_angle": target,
                    "actual_angle": actual,
                    "reached": int(reached),
                    "time_to_reach_s": f"{elapsed:.3f}",
                    "status": last.get("status", []),
                    "force": last.get("force", []),
                    "error": last.get("error", []),
                }
                writer.writerow(row)
                file.flush()
                print(row)

                if not reached:
                    hand.stop_motion()
                    raise TimeoutError(
                        f"Finger {args.finger} did not reach {target} "
                        f"within {args.timeout:.1f}s; speed stopped."
                    )


if __name__ == "__main__":
    main()
