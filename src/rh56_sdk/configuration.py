"""Configuration objects for the RH56 SDK."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JointLimit:
    """Inclusive command range for one RH56 channel."""

    minimum: int
    maximum: int


@dataclass(frozen=True)
class HandLimits:
    """Six-channel command limits in RH56 vector order."""

    pinky: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    ring: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    middle: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    index: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))
    thumb_flex: JointLimit = field(default_factory=lambda: JointLimit(200, 700))
    thumb_rotation: JointLimit = field(default_factory=lambda: JointLimit(0, 1000))

    def as_tuple(self) -> tuple[JointLimit, JointLimit, JointLimit, JointLimit, JointLimit, JointLimit]:
        return (
            self.pinky,
            self.ring,
            self.middle,
            self.index,
            self.thumb_flex,
            self.thumb_rotation,
        )


CONSERVATIVE_LIMITS = HandLimits()
FACTORY_LIMITS = HandLimits(
    thumb_flex=JointLimit(200, 1000),
)


@dataclass(frozen=True)
class RetryPolicy:
    timeout: float = 0.1
    retries: int = 2
    retry_delay: float = 0.01


@dataclass(frozen=True)
class FaultPolicy:
    stale_after: int = 3
    fault_after: int = 5


@dataclass(frozen=True)
class RH56Config:
    """Configuration for one RH56 driver instance."""

    port: str
    baud: int = 115200
    node_id: int = 1
    timeout: float = 0.1
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    fault: FaultPolicy = field(default_factory=FaultPolicy)
    limits: HandLimits = field(default_factory=lambda: CONSERVATIVE_LIMITS)
