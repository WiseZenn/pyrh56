# pyrh56

[![CI](https://github.com/WiseZenn/pyrh56/actions/workflows/ci.yml/badge.svg)](https://github.com/WiseZenn/pyrh56/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyrh56)](https://pypi.org/project/pyrh56/)
[![Python](https://img.shields.io/pypi/pyversions/pyrh56)](https://pypi.org/project/pyrh56/)
[![License](https://img.shields.io/pypi/l/pyrh56)](https://github.com/WiseZenn/pyrh56/blob/main/LICENSE)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/type-mypy-blue)](https://github.com/python/mypy)

[中文](README_CN.md)

A low-level Python driver for the Inspire Robots RH56 6-DOF dexterous hand —
serial transport, protocol codec, validated writes, feedback, fault handling,
calibration, and diagnostics.

> This is an independent project. It is **not** affiliated with or endorsed by
> Inspire Robots. "RH56" is used solely to identify the compatible hardware.

---

## Install

```
pip install pyrh56
```

Python ≥ 3.10. Runtime dependency: [pyserial](https://github.com/pyserial/pyserial).

The PyPI package is `pyrh56`; the import package is `rh56_sdk`:

```python
from rh56_sdk import RH56Config, RH56Driver
```

Dev install:

```
pip install -e ".[dev]"
```

---

## Quick Start

```python
from rh56_sdk import RH56Config, RH56Driver

with RH56Driver("COM3") as hand:
    hand.move_to([1000, 1000, 1000, 1000, 1000, 900])  # open
    angle  = hand.read_angle()
    force  = hand.read_force()
    status = hand.read_status()
```

Mock mode — no hardware needed:

```python
hand = RH56Driver.mock()
hand.connect()
hand.read_angle()  # → [0, 0, 0, 0, 0, 0]
```

---

## Command line

The command is `pyrh56`, matching the distribution name. Install this development version with
`pip install -e .`.

```console
pyrh56 ports
pyrh56 --port COM3 ping
pyrh56 --port COM3 state
pyrh56 --port COM3 doctor
pyrh56 --port COM3 watch --fields angle,force --count 100 --jsonl > feedback.jsonl
pyrh56 --mock state --json
```

Commands also include `move`, `finger`, `open`, `close`, `stop`, `speed`, `force`, `clear-error`,
and `calibrate`. Use `--help` for each command. Common options work before or after the command;
hardware commands require `--port`. `--mock` returns zero feedback and does not simulate motion.
`--wait` checks actual angle feedback; a write ACK alone does not mean the target was reached.
`python -m rh56_sdk` provides the same interface.
`finger` writes only the selected channel register. Unknown status codes produce a diagnostic
warning; inspect `health_verified` as well as the command exit code.

See the [CLI reference (Chinese)](docs/cli.md), [development plan](docs/development-plan.md),
the [official driver review](docs/official-driver-review.md), and the
[COM13 hardware test report](docs/hardware-test-report.md).

---

## Protocol

The RH56 uses a private RS-232/RS-485 binary protocol, checked against manual V1.09.
CAN and Modbus are not implemented by this package.

| Direction | Frame |
|-----------|-------|
| Host → RH56 | `EB 90` ID Len CMD Payload… Checksum |
| RH56 → Host | `90 EB` ID Len CMD Payload… Checksum |

- All 16-bit data is little-endian.
- Checksum = low 8 bits of the byte sum over everything after the header.
- Implementation: [src/rh56_sdk/protocol.py](src/rh56_sdk/protocol.py).

---

## API

### Connection

`connect()`, `disconnect()`, `is_connected` — built on `pyserial`, transaction-locked.

### Motion

| Method | Description |
|--------|-------------|
| `move_to(frame)` | Write 6-channel frame with validation and limits |
| `move_finger(i, value)` | Single-finger incremental, based on last command frame |
| `move_finger(i, value, base="hold")` | Write only the selected channel; preserve other register targets |
| `set_speed(values)` | 6-channel speed (0–1000) |
| `set_force_threshold(values)` | 6-channel force threshold (0–1000) |
| `stop_motion()` | Request zero speed and verify ACK; COM13 showed movement after ACK, so immediate stopping is not guaranteed |
| `check_motion_ready()` | Read STATUS/ERROR and reject hardware faults |
| `wait_until_reached(target)` | Poll actual angles; `None` skips a channel; raise on fault or timeout |
| `commanded_angle` | Copy of the latest synchronized or acknowledged target frame |
| `recover_open_unchecked(confirm=True)` | Emergency open, bypass ACK validation |

### Feedback

`read_angle()`, `read_actuator_position()`, `read_force()`, `read_current()`,
`read_voltage()`, `read_status()`, `read_error()`, `read_temperature()`,
`read_feedback()`.

Each read retries up to 3 times (100 ms timeout, 10 ms interval). Consecutive
failures trigger communication fault detection.

### Fault Handling

| Method / Attribute | Description |
|--------------------|-------------|
| `clear_error()` | Write CLEAR_ERROR=1, re-read STATUS/ERROR to verify |
| `safe_stop` | Auto-set on hardware fault; blocks motion commands |
| `communication_fault` | Set when consecutive read failures reach threshold |
| `miss_count`, `is_stale`, `feedback_age` | Read health status |
| `reset_miss_count()` | Reset the communication fault counter |

### Calibration & Diagnostics

Separated from the driver core — accessed via standalone objects:

```python
from rh56_sdk.calibration import ForceCalibration
from rh56_sdk.diagnostics import RH56Diagnostics

cal = ForceCalibration(hand)
cal.run_official(wait=True, require_confirm=False)   # hardware force calibration
cal.measure_baseline(samples=50)                      # software zero baseline
cal.validate_baseline(tolerance=30)                   # zero validation
cal.get_net_force()                                   # net force (zero offset removed)
cal.save_profile("baseline.json")                     # save calibration profile

diag = RH56Diagnostics(hand)
snapshot = diag.read_feedback_snapshot()              # typed feedback snapshot
diag.characterize_angle_tracking(require_confirm=False)  # angle tracking characterization
```

---

## Exceptions

```
RH56Error
├── RH56ConnectionError
│   └── RH56NotConnectedError
├── RH56ProtocolError
│   ├── RH56ChecksumError
│   └── RH56FrameError
├── RH56SafetyError
│   ├── RH56BusyError
│   ├── RH56ValidationError
│   │   └── RH56ServoLimitError
│   └── RH56HardwareError
│       └── RH56CalibrationError
└── RH56TimeoutError
```

---

## Architecture

```
examples/          ← 15 standalone example scripts
rh56_grasp/        ← high-level grasp control (pre-shape, force-aware close, state machine)
src/rh56_sdk/
├── transport.py   ← serial abstraction (pyserial + mock)
├── protocol.py    ← binary protocol codec
├── safety.py      ← frame validation & clamping
├── driver.py      ← unified public API
├── cli.py         ← pyrh56 terminal commands (thin SDK wrapper)
├── calibration.py ← force sensor calibration
├── diagnostics.py ← feedback snapshots & characterization
├── configuration.py, constants.py, enums.py, exceptions.py, models.py, registers.py
tests/             ← SDK and CLI tests, no hardware required
```

Dependency direction: `examples / grasp → driver → protocol / safety → transport`

---

## Safety

- Defaults to `DEFAULT_LIMITS` (all channels 0–1000), matching the manual's explicit angle range.
  Use `CONSERVATIVE_LIMITS` or CLI `--conservative-limits` for the previous 200–700 range.
  The existing `FACTORY_LIMITS` profile keeps its previous 200–1000 thumb range for compatibility.
  Optional narrower ranges and the 900 thumb-rotation preset are project policies.
- All writes validated before serial encoding: length (must be 6), type (rejects
  bool/NaN/Inf), range per-finger.
- Reading a hardware fault latches `safe_stop`, blocking subsequent motion until `clear_error()`
  succeeds. This software flag does not send a hardware stop command.
- `recover_open_unchecked` requires `confirm=True` to execute.

---

## Development

```
pytest                     # SDK/CLI tests, no hardware required
ruff check .               # lint, line-length=100
mypy src/rh56_sdk          # type check
```

CI covers Windows / macOS / Linux, Python 3.10–3.13, with CodeQL and 70%
coverage threshold. Pre-commit hooks are configured (`.pre-commit-config.yaml`).

---

## Examples

| File | Description |
|------|-------------|
| [01_list_ports.py](examples/01_list_ports.py) | Enumerate serial ports |
| [02_connect.py](examples/02_connect.py) | Connect & disconnect |
| [03_open_close.py](examples/03_open_close.py) | Open & close hand |
| [04_single_finger.py](examples/04_single_finger.py) | Single-finger control |
| [05_set_speed.py](examples/05_set_speed.py) | Speed configuration |
| [06_set_force_threshold.py](examples/06_set_force_threshold.py) | Force threshold |
| [07_read_state.py](examples/07_read_state.py) | Read angle/force/status |
| [08_read_feedback.py](examples/08_read_feedback.py) | Composite feedback read |
| [09_move_and_readback.py](examples/09_move_and_readback.py) | Move & readback |
| [10_safety_test.py](examples/10_safety_test.py) | Safety validation |
| [11_diagnostics.py](examples/11_diagnostics.py) | Diagnostic snapshots |
| [13_force_calibration.py](examples/13_force_calibration.py) | Force calibration |
| [14_force_zero_validation.py](examples/14_force_zero_validation.py) | Zero validation |
| [15_angle_tracking_characterization.py](examples/15_angle_tracking_characterization.py) | Angle tracking |
| [16_grasp_controller_demo.py](examples/16_grasp_controller_demo.py) | High-level grasp |

---

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This project is an independent Python driver. It is **not** developed by,
affiliated with, endorsed by, or sponsored by **Inspire Robots**
(因时机器人). "RH56" is used solely as a descriptive reference to the
compatible hardware product.

The communication protocols were derived from publicly available documentation
for interoperability purposes. No proprietary software or firmware is distributed.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND. Users are
responsible for validating all commands before sending them to physical hardware
and for ensuring compliance with applicable laws.
