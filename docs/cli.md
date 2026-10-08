# pyrh56 命令行工具

`pyrh56` 是发行包与终端命令的名称，Python 导入名为 `rh56_sdk`。这是面向 RH56 私有串口协议的独立工具，不代表因时机器人官方产品。

## 安装与首次使用

安装或升级 PyPI 发行版（CLI 需要 0.4.0 及后续版本）：

```console
python -m pip install --upgrade pyrh56
pyrh56 --version
pyrh56 --help
```

同一个入口也可以通过 `python -m rh56_sdk` 使用。
从源码开发时，在仓库目录运行 `python -m pip install -e .`。

先列出串口适配器，再选择串口验证通信：

```console
pyrh56 ports
pyrh56 --port COM3 ping
pyrh56 --port COM3 state
pyrh56 --port COM3 doctor
```

Linux/macOS 将 `COM3` 换成实际的 `/dev/ttyUSB0` 或 `/dev/cu.*` 端口。`ports` 不打开串口，不探测设备；列出的 USB 适配器未必连接 RH56。
`ping` 要求收到且校验通过 ANGLE_ACT 响应，打开串口本身不算设备响应。

无需硬件的演示：

```console
pyrh56 --mock state --json
pyrh56 watch --mock --fields angle,force --count 3 --jsonl
pyrh56 --mock doctor
```

Mock 始终返回零反馈，写指令生成模拟 ACK；它不模拟手指运动。因此 `--mock open --wait` 会到位超时。

## 连接选项与单位

通用选项可以放在子命令前或后：

```console
pyrh56 --port COM3 --id 1 state --json
pyrh56 state --port COM3 --id 1 --json
```

| 选项 | 默认与含义 |
| --- | --- |
| `--port` | 实机操作必填；不自动选择设备 |
| `--mock` | 显式使用 Mock；与 `--port` 互斥 |
| `--baud` | 115200；亦支持手册规定的 57600、19200 |
| `--id` | 1；设备 ID 范围 1–254 |
| `--timeout` | 0.1 秒；每次请求的超时，读取另有默认 2 次重试 |
| `--conservative-limits` | 可选保守限位；拇指弯曲 200–700 |
| `--factory-limits` | 保留旧的拇指 200–1000 配置；与保守选项互斥；默认无需此选项 |
| `--json` | 单次结果输出 JSON |
| `--jsonl` | `watch` 每次采样输出一行 JSON |

所有六通道向量的顺序为：`pinky, ring, middle, index, thumb_flex, thumb_rotation`。

- 角度：设备 0–1000 标度，不是度数。0 更弯曲，1000 更张开。
- 默认六个通道均为 0–1000，与手册的明确角度范围一致；可用 `--conservative-limits` 将拇指弯曲范围收窄至 200–700。可选较窄范围属于项目策略，不能当作硬件安全认证。
- 速度与力控阈值：设备 0–1000 设置标度，不作物理单位换算。
- 实际力：手册以 g 表示；保留有符号 short 解码，负数的物理意义未由手册解释。
- 电流：mA；温度：摄氏度。电压报告寄存器原始值，未推断 V/mV 换算。
- 当前明确目标 API 不接受手册的 `-1` 不动作哨兵值。

## 反馈与诊断

```console
pyrh56 --port COM3 state --fields angle,force,status,error
pyrh56 --port COM3 watch --fields angle,force --interval 0.1 --count 100 --jsonl > feedback.jsonl
pyrh56 --port COM3 doctor --json
```

字段可选 `angle,force,status,error,current,temperature,voltage`。状态和错误输出同时保留原始值及解释；`status_known` 表示每个状态码是否在当前手册映射中。
`watch --count 0`（默认）持续运行，Ctrl+C 返回 130 并关闭串口。它是只读采集，中断不会发送运动/停止指令。
`--interval` 是完整采样之间的延迟，不保证固定频率。多个字段按顺序读取，不构成同步硬件快照。

`doctor` 尝试打开串口并读取各反馈字段，某字段失败后继续检查其余字段，返回错误详情和检查建议。
诊断不会校准、清错或移动手指，也不会把 Mock 结果作为真机健康证明。
`state` 的成功表示查询完成；是否有设备故障需查看其 `status`/`error`。`doctor` 对故障或采集失败返回非零退出码。
未知状态码（例如本次真机返回的 255）显示 `WARN`，对应检查的 `ok: null`、`severity: "warning"`，并设置 `health_verified: false`。
仅有未知状态警告时退出码仍为 0，表示诊断采集完成；它不代表已验证设备健康。Mock 的 `health_verified` 也始终为 false。
`health_verified` 仅涵盖反馈采集与 STATUS/ERROR 检查，不包含力零位精度；即使 `doctor` 通过，`calibrate validate` 仍可能报告力零位超出容差。

## 控制

```console
pyrh56 --port COM3 speed 100 100 100 100 100 100
pyrh56 --port COM3 force 100 100 100 100 100 100
pyrh56 --port COM3 open
pyrh56 --port COM3 close
pyrh56 --port COM3 move --angles 1000 1000 1000 1000 1000 900 --wait
pyrh56 --port COM3 finger index 800 --wait --wait-timeout 5
pyrh56 --port COM3 stop
pyrh56 --port COM3 clear-error
```

控制和参数设置前重新读取 STATUS/ERROR。每次 CLI 启动都会创建新的驱动对象，不能依赖上一进程保存的故障标记。
`open` 默认张开预设为 `[1000, 1000, 1000, 1000, 1000, 900]`，根据选定的配置限位生成目标；使用 `--conservative-limits` 时拇指弯曲目标为 700。用户显式提供的 `move --angles` 不会自动限幅。
`close` 默认闭合预设为 `[0, 0, 0, 0, 0, 900]`；使用保守或旧的 factory 配置时，拇指弯曲闭合目标为 200。拇指旋转预设继续使用 900，不等同于旋转通道的限位。
`finger` 只写所选通道的一个 ANGLE_SET short，校验该通道限位，不改写其他五个通道的目标寄存器。
其他通道继续执行原有目标；此操作不会冻结已经在运动的其他手指。所有通道的硬件故障仍会阻止运动。

未加 `--wait` 时，成功结果只有 `acknowledged: true`，`reached: null`；ACK 表示寄存器写入成功。
`--wait` 比较实际角度与目标（默认容差 20），期间检查故障。单指命令只比较所选通道，JSON `target` 的其他位置为 `null`；全帧命令比较六个通道。力控到位不能替代角度到位。
默认等待超时 5 秒、轮询间隔 0.05 秒；在途读取仍可能消耗其请求与重试预算。

运动命令已开始后若通信/等待失败或被 Ctrl+C 中断，工具在关闭串口前尝试零速度写入，并报告是否收到 ACK。
参数校验或运动前故障检查失败，不会发出运动或零速度恢复指令。
`stop` 本身不依赖角度同步，并允许在软件标记的标定期间尝试零速度写入。
官方手册未明确零速急停效果，因此 ACK 不证明硬件已经停止；断线时也无法保证停止。
本次 COM13 空载测试中，零速 ACK 后食指仍变化 10 个设备刻度才保持稳定，见[真机测试报告](hardware-test-report.md)。该观测不是所有速度、负载和固件的停止性能保证。
零速度会保留在设备运行参数中，下次运动前请显式设置所需速度。

`clear-error` 写清错寄存器后重新读取 ERROR/STATUS；故障仍存在会返回失败。手册说明过温不能被强制清除。

## 力标定与零位配置

```console
pyrh56 --port COM3 calibrate force --confirm
pyrh56 --port COM3 calibrate validate --samples 20 --tolerance 30
pyrh56 --port COM3 calibrate baseline --confirm --samples 50 --profile baseline.json
pyrh56 --port COM3 calibrate validate --profile baseline.json --samples 20
```

`force` 调用硬件标定，手会自行张开/弯曲；`--confirm` 确认空载条件。手册过程约 6 秒，默认软件等待 8 秒，`--wait-seconds` 不得小于 6。
结果报告已等待的时间和标定后故障检查；独立零位验证仍需执行 `validate`，不能仅凭计时宣布力传感器精度达标。
本进程被中断时，SDK 保留尚未结束的标定互斥时间；新进程无法继承该状态，需先确保设备标定已经结束。

`baseline` 采样并计算六通道中位数偏移，仅作用于软件，不写设备 Flash。
`validate` 无配置时检查原始力零位；提供 `--profile` 时先加载该偏移，再检查扣除偏移后的力。
配置应对应同一设备和测量条件；目前 JSON 不绑定设备序列号。

## 脚本输出与退出码

JSON/JSONL 的 `schema_version` 当前为 1。正常结果写 stdout；错误对象写 stderr，成功数据流不混入日志或 traceback。
机器输出对非 ASCII 字符作 JSON 转义，便于在 Windows 本地编码的管道中交给 UTF-8 读取器；解析后保留原始中文名称。
`doctor` 的失败检查报告写 stdout 并返回非零；解析/连接等错误写 stderr。

```json
{"schema_version":1,"command":"state","ok":true,"timestamp":1790726400.0,"mock":true,"port":"COM_MOCK","node_id":1,"data":{"angle":[0,0,0,0,0,0]}}
```

`watch` 另有从 1 开始的 `sequence`。错误对象包含 `error.type`、`message`、`exit_code`、`hint`。
运动失败的错误对象另有 `recovery`，分别报告零速度 ACK 与硬件停止是否得到验证。

| 退出码 | 含义 |
| --- | --- |
| 0 | 命令成功；下游关闭输出管道也正常结束 |
| 1 | 文件或其他 SDK 运行错误 |
| 2 | 参数、配置或输入文件格式不合法 |
| 3 | 串口连接失败 |
| 4 | 超时或协议错误 |
| 5 | 设备故障、操作互斥或诊断/零位验证不通过 |
| 130 | Ctrl+C 中断 |

## SDK 新接口与支持边界

```python
from rh56_sdk import RH56Config, RH56Driver
from rh56_sdk.transport import SerialTransport

ports = SerialTransport.list_port_info()
config = RH56Config("COM3", timeout=0.2)
# RetryPolicy(timeout=...) 可显式覆盖请求超时；默认继承 config.timeout。
with RH56Driver(config) as hand:
    hand.check_motion_ready()
    hand.move_to([1000, 1000, 1000, 1000, 1000, 900])
    actual = hand.wait_until_reached(hand.commanded_angle)
```

`move_to()` 保留已有缓存故障检查，不默认额外轮询寄存器；控制序列开始时显式调用 `check_motion_ready()`。
`commanded_angle` 返回副本。读取反馈与标定模块继续独立于 CLI。
默认配置为 `DEFAULT_LIMITS`，六通道均为 0–1000；可通过 `RH56Config("COM3", limits=CONSERVATIVE_LIMITS)` 选择旧的拇指 200–700 范围，`CONSERVATIVE_LIMITS` 从 `rh56_sdk` 导入。`FACTORY_LIMITS` 仍保留旧的拇指 200–1000 配置。
`move_finger(i, value, base="hold")` 只写单通道寄存器；已有默认 `base="last_command"` 和 `base="actual"` 保留六通道组帧行为。
单通道到位等待可使用 `hand.wait_until_reached([None, None, None, 800, None, None])`；`None` 只用于软件等待，不写到设备。
本版支持经过协议核对的 RH56 私有串口路径；没有实现 CAN、Modbus、固件升级、自动探测所有串口或高级抓取 CLI。
已在 COM13 完成空载食指测试，型号/固件覆盖和负载场景仍待验收，参见[真机测试报告](hardware-test-report.md)、[开发计划](development-plan.md)与[官方资料核查](official-driver-review.md)。
