"""Small explicit state machine for high-level grasp workflows."""

from enum import Enum


class GraspState(str, Enum):
    IDLE = "IDLE"
    OPEN = "OPEN"
    PRE_SHAPE = "PRE_SHAPE"
    CLOSING = "CLOSING"
    CONTACT_DETECTED = "CONTACT_DETECTED"
    HOLD = "HOLD"
    RELEASE = "RELEASE"
    ERROR = "ERROR"


_ALLOWED: dict[GraspState, set[GraspState]] = {
    GraspState.IDLE: {GraspState.OPEN, GraspState.PRE_SHAPE, GraspState.ERROR},
    GraspState.OPEN: {GraspState.PRE_SHAPE, GraspState.RELEASE, GraspState.ERROR},
    GraspState.PRE_SHAPE: {GraspState.CLOSING, GraspState.OPEN, GraspState.ERROR},
    GraspState.CLOSING: {
        GraspState.CONTACT_DETECTED,
        GraspState.HOLD,
        GraspState.RELEASE,
        GraspState.ERROR,
    },
    GraspState.CONTACT_DETECTED: {GraspState.HOLD, GraspState.RELEASE, GraspState.ERROR},
    GraspState.HOLD: {GraspState.RELEASE, GraspState.ERROR},
    GraspState.RELEASE: {GraspState.OPEN, GraspState.IDLE, GraspState.ERROR},
    GraspState.ERROR: {GraspState.RELEASE, GraspState.IDLE},
}


class GraspStateMachine:
    """Validate grasp-controller state transitions."""

    def __init__(self) -> None:
        self.state = GraspState.IDLE

    def transition(self, new_state: GraspState) -> None:
        """Move to *new_state* or raise ValueError if the transition is invalid."""
        if new_state not in _ALLOWED[self.state]:
            raise ValueError(f"Invalid state transition: {self.state} -> {new_state}")
        self.state = new_state

    def force(self, new_state: GraspState) -> None:
        """Set state directly for exception cleanup paths."""
        self.state = new_state
