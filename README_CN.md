# pyrh56

[![CI](https://github.com/WiseZenn/pyrh56/actions/workflows/ci.yml/badge.svg)](https://github.com/WiseZenn/pyrh56/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyrh56)](https://pypi.org/project/pyrh56/)
[![Python](https://img.shields.io/pypi/pyversions/pyrh56)](https://pypi.org/project/pyrh56/)
[![License](https://img.shields.io/pypi/l/pyrh56)](https://github.com/WiseZenn/pyrh56/blob/main/LICENSE)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/type-mypy-blue)](https://github.com/python/mypy)

[English](README.md)

Inspire Robots RH56 六自由度灵巧手的底层 Python 驱动——串口通信、协议编解码、指令
校验、状态反馈、故障处理、标定与诊断。

> 这是个人独立项目，与 **因时机器人（北京因时机器人科技有限公司）**（Inspire Robots）无任何
> 关联或认可关系。"RH56" 仅用于标识兼容硬件产品。

---

## 安装

```
pip install pyrh56
```

Python ≥ 3.10。运行时仅依赖 [pyserial](https://github.com/pyserial/pyserial)。

PyPI 包名 `pyrh56`，导入包名 `rh56_sdk`：

```python
from rh56_sdk import RH56Config, RH56Driver
```

开发安装：

```
pip install -e ".[dev]"
```

---

## 快速开始

```python
from rh56_sdk import RH56Config, RH56Driver

with RH56Driver("COM3") as hand:
    hand.move_to([1000, 1000, 1000, 1000, 1000, 900])   # 张开
    angle  = hand.read_angle()
    force  = hand.read_force()
    status = hand.read_status()
```

Mock 模式——无需硬件：

```python
hand = RH56Driver.mock()
hand.connect()
hand.read_angle()  # → [0, 0, 0, 0, 0, 0]
```

---

## 命令行

命令名为 `pyrh56`，与 PyPI 包一致；当前开发版本可用 `pip install -e .` 安装。

```console
pyrh56 ports
pyrh56 --port COM3 ping
pyrh56 --port COM3 state
pyrh56 --port COM3 doctor
pyrh56 --port COM3 watch --fields angle,force --count 100 --jsonl > feedback.jsonl
pyrh56 --mock state --json
```

控制命令包括 `move`、`finger`、`open`、`close`、`stop`、`speed`、`force`、`clear-error` 和 `calibrate`。
`--wait` 通过实际角度判断到位；写 ACK 不代表动作完成。Mock 始终返回零反馈，不模拟动作。
`finger` 只写所选通道寄存器。未知状态码产生诊断警告；除退出码外，还应查看 `health_verified`。
也支持 `python -m rh56_sdk`。完整用法、单位、JSON 输出与退出码见[CLI 文档](docs/cli.md)。
实现范围与验证记录见[开发计划](docs/development-plan.md)、[官方驱动核查](docs/official-driver-review.md)和[COM13 真机测试报告](docs/hardware-test-report.md)。

---

## 协议

RH56 使用 RS-232/RS-485 私有二进制协议（已对照官网 V1.09 手册）；本包没有实现 CAN/Modbus。

| 方向 | 帧结构 |
|------|--------|
| Host → RH56 | `EB 90` ID Len CMD Payload… Checksum |
| RH56 → Host | `90 EB` ID Len CMD Payload… Checksum |

- 16 位数据均为小端序。
- 校验和 = 帧头之后所有字节累加的低 8 位。
- 实现详见 [src/rh56_sdk/protocol.py](src/rh56_sdk/protocol.py)。

---

## API

### 连接

`connect()`, `disconnect()`, `is_connected` — 基于 `pyserial`，事务级锁定。

### 运动

| 方法 | 说明 |
|------|------|
| `move_to(frame)` | 六通道全帧写入，带校验与限位 |
| `move_finger(i, value)` | 单指增量控制，默认基于上次指令帧 |
| `move_finger(i, value, base="hold")` | 只写所选通道，保留其他通道原目标寄存器 |
| `set_speed(values)` | 六通道速度 (0–1000) |
| `set_force_threshold(values)` | 六通道力控阈值 (0–1000) |
| `stop_motion()` | 请求零速度并等待 ACK；COM13 实测 ACK 后仍有位移，不能保证即时停止 |
| `check_motion_ready()` | 读取 STATUS/ERROR，检查当前硬件故障 |
| `wait_until_reached(target)` | 轮询实际角度，`None` 跳过该通道；故障或超时抛出异常 |
| `commanded_angle` | 最近同步或写入成功的目标帧副本 |
| `recover_open_unchecked(confirm=True)` | 紧急张开，跳过 ACK 校验 |

### 反馈

`read_angle()`, `read_actuator_position()`, `read_force()`, `read_current()`,
`read_voltage()`, `read_status()`, `read_error()`, `read_temperature()`,
`read_feedback()`。

每次读取内置重试（默认 3 次，100 ms 超时，10 ms 间隔）。连续失败触发通信故障检测。

### 故障处理

| 方法/属性 | 说明 |
|-----------|------|
| `clear_error()` | 写 CLEAR_ERROR=1，重读 STATUS/ERROR 验证清除 |
| `safe_stop` | 硬件故障后自动置位，阻塞运动指令 |
| `communication_fault` | 连续读取失败达阈值后置位 |
| `miss_count`, `is_stale`, `feedback_age` | 读取健康状态 |
| `reset_miss_count()` | 重置通信故障计数器 |

### 标定与诊断

与驱动核心分离，通过独立对象调用：

```python
from rh56_sdk.calibration import ForceCalibration
from rh56_sdk.diagnostics import RH56Diagnostics

cal = ForceCalibration(hand)
cal.run_official(wait=True, require_confirm=False)   # 启动力传感器硬件标定
cal.measure_baseline(samples=50)                      # 软件侧零位基准
cal.validate_baseline(tolerance=30)                   # 零位验证
cal.get_net_force()                                   # 净力（扣除零位偏移）
cal.save_profile("baseline.json")                     # 保存标定配置

diag = RH56Diagnostics(hand)
snapshot = diag.read_feedback_snapshot()              # 类型化反馈快照
diag.characterize_angle_tracking(require_confirm=False)  # 角度跟踪特性
```

---

## 异常体系

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

## 架构

```
examples/          ← 15 个独立示例脚本
rh56_grasp/        ← 高级抓取控制（预塑形、力感知闭合、状态机、日志）
src/rh56_sdk/
├── transport.py   ← 串口抽象（pyserial + mock）
├── protocol.py    ← 二进制协议编解码
├── safety.py      ← 指令帧校验与限幅
├── driver.py      ← 统一公开 API
├── cli.py         ← pyrh56 命令行（直接复用 SDK）
├── calibration.py ← 力传感器标定
├── diagnostics.py ← 反馈快照与特性测试
├── configuration.py, constants.py, enums.py, exceptions.py, models.py, registers.py
tests/             ← SDK 与 CLI 测试，无需硬件
```

分层依赖：`examples / grasp → driver → protocol / safety → transport`

---

## 安全设计

- 默认 `DEFAULT_LIMITS` 六个通道范围均为 0–1000，与手册的明确角度范围一致。需要原来的拇指 200–700 范围可传入 `CONSERVATIVE_LIMITS`，CLI 使用 `--conservative-limits`。
  已有 `FACTORY_LIMITS` 保留旧的拇指 200–1000 配置以兼容现有代码；可选较窄范围和 900 旋转预设仍是项目策略。
- 所有写入前校验：长度（必须 6 值）、类型（拒绝 bool/NaN/Inf）、范围逐指检查。
- 读取状态发现故障后 `safe_stop` 置位，阻塞后续运动指令直到 `clear_error()` 成功；该标记不等于已发送硬件停止指令。
- `recover_open_unchecked` 需 `confirm=True` 显式确认。

---

## 开发

```
pytest                     # SDK/CLI 测试，无需硬件
ruff check .               # lint, line-length=100
mypy src/rh56_sdk          # 类型检查
```

CI 覆盖 Windows / macOS / Linux，Python 3.10–3.13，含 CodeQL 安全扫描和 70% 覆盖率
阈值。已配置 pre-commit hooks（`.pre-commit-config.yaml`）。

---

## 示例

| 文件 | 内容 |
|------|------|
| [01_list_ports.py](examples/01_list_ports.py) | 枚举串口 |
| [02_connect.py](examples/02_connect.py) | 连接与断开 |
| [03_open_close.py](examples/03_open_close.py) | 张手 / 握手 |
| [04_single_finger.py](examples/04_single_finger.py) | 单指控制 |
| [05_set_speed.py](examples/05_set_speed.py) | 速度配置 |
| [06_set_force_threshold.py](examples/06_set_force_threshold.py) | 力控阈值 |
| [07_read_state.py](examples/07_read_state.py) | 读取角度/力/状态 |
| [08_read_feedback.py](examples/08_read_feedback.py) | 组合反馈读取 |
| [09_move_and_readback.py](examples/09_move_and_readback.py) | 运动与回读 |
| [10_safety_test.py](examples/10_safety_test.py) | 安全校验测试 |
| [11_diagnostics.py](examples/11_diagnostics.py) | 诊断快照 |
| [13_force_calibration.py](examples/13_force_calibration.py) | 力传感器标定 |
| [14_force_zero_validation.py](examples/14_force_zero_validation.py) | 零位验证 |
| [15_angle_tracking_characterization.py](examples/15_angle_tracking_characterization.py) | 角度跟踪特性 |
| [16_grasp_controller_demo.py](examples/16_grasp_controller_demo.py) | 高级抓取控制 |

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)。

## 免责声明

本项目是个人独立开发的 Python 驱动，与 **因时机器人（北京因时机器人科技有限公司）**
（Inspire Robots）无任何关联、认可或赞助关系。"RH56" 仅用于标识兼容硬件产品。

通信协议基于公开可用文档以实现互操作性目的。本项目不包含、不分发任何 Inspire
Robots 的专有软件或固件。

本软件按"现状"提供，不附带任何形式的保证。使用者在向物理硬件发送指令前应自行
验证安全性，并确保遵守适用法律法规。
