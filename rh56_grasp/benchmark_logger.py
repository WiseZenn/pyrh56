"""Trial logging helpers for RH56 grasp experiments."""

import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable


TRIAL_FIELDS = [
    "trial_id",
    "timestamp",
    "object_name",
    "object_size",
    "object_weight",
    "object_material",
    "grasp_type",
    "target_frame",
    "speed",
    "force_threshold",
    "actual_position",
    "force_curve",
    "max_force",
    "closing_time",
    "hold_time",
    "success",
    "failure_reason",
]


class BenchmarkLogger:
    """Append trial records as CSV or JSONL."""

    def __init__(self, path: str = "rh56_grasp_trials.csv") -> None:
        self.path = Path(path)

    def next_trial_id(self) -> int:
        """Return the next integer trial id based on existing log rows."""
        if not self.path.exists():
            return 1
        if self.path.suffix.lower() == ".jsonl":
            with self.path.open("r", encoding="utf-8") as file:
                return sum(1 for line in file if line.strip()) + 1
        with self.path.open("r", newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
            return len(rows) + 1

    def log(self, record: Dict[str, Any]) -> None:
        """Append one trial record."""
        normalized = self._normalize_record(record)
        if self.path.suffix.lower() == ".jsonl":
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(normalized, ensure_ascii=False) + "\n")
            return

        write_header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=TRIAL_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(normalized)

    def _normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {field: record.get(field, "") for field in TRIAL_FIELDS}
        normalized["timestamp"] = normalized["timestamp"] or time.time()
        for field in ("target_frame", "actual_position", "force_curve"):
            if isinstance(normalized[field], (list, dict, tuple)):
                normalized[field] = json.dumps(normalized[field], ensure_ascii=False)
        return normalized


def max_abs_force(samples: Iterable[Iterable[int]]) -> int:
    """Return maximum absolute force seen in a force curve."""
    maximum = 0
    for sample in samples:
        for value in sample:
            maximum = max(maximum, abs(int(value)))
    return maximum
