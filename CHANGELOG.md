# Changelog

## 0.4.0 (2026-10-08)

- Add the `pyrh56` console command and `python -m rh56_sdk` entry point with no new runtime dependency.
- Add serial adapter listing, verified ping, feedback snapshots/streams, read-only diagnostics,
  motion presets/full-frame/single-finger control, speed/force settings, fault clearing and calibration.
- Provide JSON/JSONL output, stable exit codes, explicit device selection and Mock mode.
- Escape non-ASCII machine output so Windows redirected pipes remain UTF-8-compatible.
- Refresh hardware faults before CLI motion; distinguish write acknowledgement from angle arrival.
- Attempt zero-speed recovery before disconnecting after motion failures or interruption.
- Validate configuration, supported baud rates, single-finger inputs and force baseline profiles.
- Make request timeouts inherit `RH56Config.timeout` unless `RetryPolicy.timeout` overrides it.
- Validate ACKs in Mock mode as well as real transport; allow zero-speed requests during calibration.
- Preserve calibration exclusivity after interruption or uncertain write acknowledgement.
- Add public readiness checks, angle-arrival polling, target copies and serial adapter metadata.
- Write only the selected ANGLE_SET register for CLI single-finger control, avoiding unrelated
  thumb-limit failures; add `move_finger(..., base="hold")` and nullable arrival-wait targets.
- Report unknown device statuses as warnings and unverified health instead of diagnostic passes.
- Change the default thumb-flex range from 200–700 to 0–1000 and open/close presets to 1000/0.
  Retain optional `CONSERVATIVE_LIMITS` / `--conservative-limits` for 200–700 and the existing
  `FACTORY_LIMITS` / `--factory-limits` profile for 200–1000. Presets respect selected limits.
- Review official adapter-driver downloads and RH56 V1.09 protocol; clarify software limits,
  zero-speed semantics, legacy constants and unsupported interfaces.
- Add regression tests, development plan, CLI documentation and a COM13 hardware test report.
- Validate empty-hand index motion through SDK/CLI and parameter restoration; observe movement
  after a zero-speed ACK, without claiming an immediate emergency stop.
- Restrict source distributions to project files, excluding local agent settings and vendor downloads.
- Add CI wheel-installation and CLI smoke checks outside the checkout on Python 3.10.

## 0.3.0

- First public release as `pyrh56` on PyPI.
- Standard `src/rh56_sdk` package layout and `pyproject.toml`.
- Typed configuration, feedback models, and public enums.
- Hardened command normalization, protocol bounds, ACK validation, and serial transactions.
- Transport injection support for tests and future bus workers.
- MIT license.
- CI across 3 OS × 4 Python versions with ruff, mypy, and CodeQL.
- Mock transport mode for no-hardware development and CI.
