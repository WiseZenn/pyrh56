import math

from rh56_sdk import RH56Driver
from rh56_sdk.constants import RH56_OPEN_FRAME
from rh56_sdk.exceptions import RH56NotConnectedError, RH56ValidationError
from rh56_sdk.safety import validate_frame


def expect_error(label, exc_type, func) -> None:
    try:
        func()
    except exc_type as exc:
        print(f"PASS {label}: {exc}")
        return
    raise AssertionError(f"FAIL {label}: expected {exc_type.__name__}")


def main() -> None:
    print("RH56 safety checks use COM_MOCK only; no hardware movement.")

    expect_error(
        "frame length must be 6",
        RH56ValidationError,
        lambda: validate_frame([1000, 1000]),
    )
    expect_error(
        "None / NaN must be rejected",
        RH56ValidationError,
        lambda: validate_frame([1000, 1000, 1000, 1000, math.nan, 900]),
    )
    expect_error(
        "move_to while disconnected must fail",
        RH56NotConnectedError,
        lambda: RH56Driver("COM_MOCK").move_to(RH56_OPEN_FRAME),
    )

    hand = RH56Driver("COM_MOCK")
    hand.connect()
    try:
        for _ in range(5):
            hand._record_read_failure(TimeoutError("simulated timeout"))
        assert hand.is_stale
        assert hand.communication_fault
        print(
            "PASS consecutive timeouts mark stale/communication_fault: "
            f"miss_count={hand.miss_count}"
        )

        hand.reset_miss_count()
        assert not hand.communication_fault
        print("PASS reset_miss_count clears communication fault")

        hand._update_safe_stop_from_status([2, 2, 5, 2, 2, 2])
        assert hand.safe_stop
        print("PASS STATUS 5/6/7 activates safe_stop")
    finally:
        hand.disconnect()


if __name__ == "__main__":
    main()
