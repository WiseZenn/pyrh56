import argparse
import time


from rh56_sdk import RH56Driver


def _status_text(hand: RH56Driver, status):
    return [hand.decode_status(code)[1] for code in status]


def _error_text(hand: RH56Driver, errors):
    decoded = []
    for error in errors:
        names = hand.decode_error(error)
        decoded.append("OK" if not names else ",".join(names))
    return decoded


def _print_snapshot(hand: RH56Driver) -> None:
    t0 = time.perf_counter()
    feedback = hand.read_feedback()
    latency_ms = (time.perf_counter() - t0) * 1000.0

    status = feedback["status"]
    errors = feedback["error"]
    print(f"RH56 connected: {hand.is_connected}")
    print(f"Angle:  {feedback['angle']}")
    print(f"Force:  {feedback['force']}")
    print(f"Status: {status} -> {_status_text(hand, status)}")
    print(f"Error:  {errors} -> {_error_text(hand, errors)}")
    print(f"Temp:   {feedback['temperature']}")
    print(f"Current:{feedback['current']}")
    print(f"Read latency: {latency_ms:.1f} ms")
    print(f"Miss count: {hand.miss_count}")
    print(f"Stale: {hand.is_stale}")
    print(f"Communication fault: {hand.communication_fault}")
    print(f"Safe stop: {hand.safe_stop}")
    if hand.last_error:
        print(f"Last error: {hand.last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RH56 command-line diagnostics.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()

    with RH56Driver(args.port, baud=args.baud) as hand:
        while True:
            _print_snapshot(hand)
            if not args.watch:
                break
            print("-" * 72)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
