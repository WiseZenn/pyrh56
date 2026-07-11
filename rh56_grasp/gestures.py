"""Reusable RH56 grasp pre-shapes.

Values use the SDK ANGLE_SET coordinate space. Lower values close fingers.
Thumb flex is kept at or above the SDK safety minimum of 200.
"""

from typing import Dict, List

GESTURES: Dict[str, List[int]] = {
    "open": [1000, 1000, 1000, 1000, 1000, 900],
    "ready_open": [1000, 1000, 1000, 1000, 700, 900],
    "fist": [0, 0, 0, 0, 200, 900],
    "pinch": [1000, 1000, 1000, 1000, 1000, 150],
    "tripod": [1000, 1000, 300, 300, 250, 900],
    "cylindrical": [150, 150, 150, 150, 300, 900],
    "hook": [100, 100, 100, 100, 700, 900],
}

MAIN_FINGERS: Dict[str, List[int]] = {
    "open": [],
    "ready_open": [],
    "fist": [0, 1, 2, 3, 4],
    "pinch": [3, 4],
    "tripod": [2, 3, 4],
    "cylindrical": [0, 1, 2, 3, 4],
    "hook": [0, 1, 2, 3],
}

CLOSURE_TARGETS: Dict[str, List[int]] = {
    "open": list(GESTURES["open"]),
    "ready_open": list(GESTURES["ready_open"]),
    "fist": list(GESTURES["fist"]),
    "pinch": [1000, 1000, 1000, 0, 200, 150],
    "tripod": [1000, 1000, 0, 0, 200, 900],
    "cylindrical": [0, 0, 0, 0, 200, 900],
    "hook": [0, 0, 0, 0, 700, 900],
}


def list_gestures() -> List[str]:
    """Return available gesture names."""
    return sorted(GESTURES)


def get_gesture(name: str) -> List[int]:
    """Return a copy of a named gesture frame."""
    try:
        return list(GESTURES[name])
    except KeyError as exc:
        raise ValueError(f"Unknown gesture: {name}") from exc


def get_closure_target(name: str) -> List[int]:
    """Return the lower-angle target used during pressure closing."""
    try:
        return list(CLOSURE_TARGETS[name])
    except KeyError as exc:
        raise ValueError(f"Unknown gesture: {name}") from exc
