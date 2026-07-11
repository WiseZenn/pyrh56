import argparse
import csv
import time


from rh56_sdk import RH56Driver


def _pad(values, width=6):
    values = list(values or [])
    return values + [""] * (width - len(values))


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only RH56 feedback logger.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--csv", default="rh56_read_feedback.csv")
    args = parser.parse_args()

    fields = (
        ["timestamp"]
        + [f"angle_{i}" for i in range(6)]
        + [f"force_{i}" for i in range(6)]
        + [f"status_{i}" for i in range(6)]
        + [f"error_{i}" for i in range(6)]
        + ["read_ok", "read_latency_ms", "miss_count", "message"]
    )

    with RH56Driver(args.port, baud=args.baud) as hand:
        with open(args.csv, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            start = time.monotonic()

            while time.monotonic() - start < args.duration:
                timestamp = time.time()
                t0 = time.perf_counter()
                read_ok = True
                message = ""
                angle = force = status = error = []

                try:
                    angle = hand.read_angle()
                    force = hand.read_force()
                    status = hand.read_status()
                    error = hand.read_error()
                except Exception as exc:
                    read_ok = False
                    message = str(exc)

                latency_ms = (time.perf_counter() - t0) * 1000.0
                row = {
                    "timestamp": f"{timestamp:.3f}",
                    "read_ok": int(read_ok),
                    "read_latency_ms": f"{latency_ms:.2f}",
                    "miss_count": hand.miss_count,
                    "message": message,
                }
                for prefix, values in (
                    ("angle", angle),
                    ("force", force),
                    ("status", status),
                    ("error", error),
                ):
                    for index, value in enumerate(_pad(values)):
                        row[f"{prefix}_{index}"] = value
                writer.writerow(row)
                file.flush()

                print(
                    f"ok={read_ok} latency={latency_ms:.1f}ms "
                    f"angle={angle} force={force} status={status} error={error} "
                    f"miss={hand.miss_count} {message}"
                )
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
