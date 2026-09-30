"""Configuration objects for the RH56 SDK."""

from dataclasses import dataclass, field
import math

from .exceptions import RH56ValidationError

SUPPORTED_BAUD_RATES = (115200, 57600, 19200)


def _check_integer(value: int, name: str, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise RH56ValidationError(f"{name} must be an integer in [{minimum}, {maximum}]")


def _check_duration(value: float, name: str, *, allow_zero: bool = False) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (value < 0 if allow_zero else value <= 0)
    ):
        comparison = ">= 0" if allow_zero else "> 0"
        raise RH56ValidationError(f"{name} must be finite and {comparison}")


@dataclass(frozen=True)
class JointLimit:
    """Inclusive command range for one RH56 channel."""

    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        _check_integer(self.minimum, "limit.minimum", 0, 1000)
        _check_integer(self.maximum, "limit.maximum", self.minimum, 1000)


@dataclass(frozen=True)
class HandLimits:
    """Six-channel command limits in RH56 vector order."""

    pinky: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    ring: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    middle: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    index: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    thumb_flex: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    thumb_rotation: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))

    def __post_init__(self) -> None:
        if not all(isinstance(limit, JointLimit) for limit in self.as_tuple()):
            raise RH56ValidationError("all hand limits must be JointLimit instances")

    def as_tuple(
        self,
    ) -> tuple[JointLimit, JointLimit, JointLimit, JointLimit, JointLimit, JointLimit]:
        return (
            self.pinky,
            self.ring,
            self.middle,
            self.index,
            self.thumb_flex,
            self.thumb_rotation,
        )


DEFAULT_LIMITS = HandLimits()
CONSERVATIVE_LIMITS = HandLimits(
    thumb_flex=JointLimit(200, 700),
)
# Retain the existing 200-1000 profile for compatibility with earlier releases.
FACTORY_LIMITS = HandLimits(thumb_flex=JointLimit(200, 1000))


@dataclass(frozen=True)
class RetryPolicy:
    timeout: float | None = None
    retries: int = 2
    retry_delay: float = 0.01

    def __post_init__(self) -> None:
        if self.timeout is not None:
            _check_duration(self.timeout, "retry.timeout")
        _check_integer(self.retries, "retry.retries", 0, 100)
        _check_duration(self.retry_delay, "retry.retry_delay", allow_zero=True)


@dataclass(frozen=True)
class FaultPolicy:
    stale_after: int = 3
    fault_after: int = 5

    def __post_init__(self) -> None:
        _check_integer(self.stale_after, "fault.stale_after", 1, 2**31 - 1)
        _check_integer(self.fault_after, "fault.fault_after", self.stale_after, 2**31 - 1)


@dataclass(frozen=True)
class RH56Config:
    """Configuration for one RH56 driver instance."""

    port: str
    baud: int = 115200
    node_id: int = 1
    timeout: float = 0.1
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    fault: FaultPolicy = field(default_factory=FaultPolicy)
    limits: HandLimits = field(default_factory=lambda: DEFAULT_LIMITS)

    def __post_init__(self) -> None:
        if not isinstance(self.port, str) or not self.port.strip():
            raise RH56ValidationError("port must be a non-empty string")
        _check_integer(self.baud, "baud", 1, 2**31 - 1)
        if self.baud not in SUPPORTED_BAUD_RATES:
            raise RH56ValidationError(f"baud must be one of {SUPPORTED_BAUD_RATES}")
        _check_integer(self.node_id, "node_id", 1, 254)
        _check_duration(self.timeout, "timeout")
        if not isinstance(self.retry, RetryPolicy):
            raise RH56ValidationError("retry must be a RetryPolicy")
        if not isinstance(self.fault, FaultPolicy):
            raise RH56ValidationError("fault must be a FaultPolicy")
        if not isinstance(self.limits, HandLimits):
            raise RH56ValidationError("limits must be HandLimits")

    @property
    def request_timeout(self) -> float:
        """Per-request timeout; an explicit retry timeout overrides the connection default."""
        return self.timeout if self.retry.timeout is None else self.retry.timeout
