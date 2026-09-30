# 官方驱动与 RH56 协议核查

核查日期：2026-09-30。范围为本项目的 RH56 六通道私有串口协议（请求帧头 `EB 90`、响应帧头 `90 EB`）。以下结论不代表所有 RH56 型号或固件，也不表示本 SDK 已支持 CAN 或 Modbus。

## 来源与下载记录

从[因时机器人灵巧手官方下载页](https://www.inspire-robots.com/support/download/dexterous%20hands/)取得驱动包与该页面当前链接的 V1.09 中文手册。下载路径中的年份不代表包内每个驱动的版本日期。

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| 官方驱动 ZIP | 18,895,782 | `10dfee7ab3f19880d7596147037731582a12f80e51dae20d5973e0c33515615d` |
| RH56 V1.09 中文手册 PDF | 2,057,718 | `30b6a09c8a750e24232f6a9630e29ad1b80578f653f922676d37e253b2ec9290` |
| ZIP 内 USB 转 CAN RAR | 16,548,157 | `c4be4247b12ab32ba110b3be6d405051b2872f1ad08835e3e8fa7d04754fdd97` |
| ZIP 内 USB 转 RS232 RAR | 2,069,347 | `a45947061f6b313d22abafcfb1e4c3779fc6cdf928c17bded256ac094a615958` |
| ZIP 内 USB 转 RS485 RAR | 283,199 | `318088fef9af8a7df21c60845a64b1ece673d7f2fd47c2461d8877185f2e0dd7` |

原始下载：[仿人五指灵巧手-驱动程序.zip](https://www.inspire-robots.com/d/file/p/2024/08-15/%E4%BB%BF%E4%BA%BA%E4%BA%94%E6%8C%87%E7%81%B5%E5%B7%A7%E6%89%8B-%E9%A9%B1%E5%8A%A8%E7%A8%8B%E5%BA%8F.zip)、[RH56 用户手册 V1.09cn.pdf](https://www.inspire-robots.com/d/file/p/2023/11-17/%E5%9B%A0%E6%97%B6%E6%9C%BA%E5%99%A8%E4%BA%BA%E4%BB%BF%E4%BA%BA%E4%BA%94%E6%8C%87%E7%81%B5%E5%B7%A7%E6%89%8B--RH56%E7%94%A8%E6%88%B7%E6%89%8B%E5%86%8CV1.09cn%20.pdf)。

下载文件、元数据、解压查阅的文本和 PDF 渲染页仅放在已忽略的 `.reference/`。未运行任何包内 EXE、安装程序、Makefile 或内核模块；未安装额外归档工具。报告不复制厂商源码，也不将驱动包加入发行物。

## 驱动包实际内容

该下载主要服务于 USB 通信适配器。CAN 分支包含通用适配器 C++ 通信库，并非本项目使用的 RH56 私有串口协议 SDK。读取了 `RT_CAN.cpp/.h`、`RT_COM.cpp/.h`、CP210x 发布记录/INF、CH341 INF 和 Linux `ch34x.c`/README/Makefile：

- CAN 通信库采用 Win32 COM API，封装通用 CAN 消息和适配器设置；适配器封包符号为 `AA`、`55`、`A5`，未发现 RH56 寄存器命令或 `EB 90` 协议实现。
- CP210x 发布记录为 6.6.1（2013-10-24）；CH341 Windows INF 为 3.5.2019.1（2019-01-30）；Linux README 声明的内核范围为 2.6.25 至 3.13.x。这些是包内记录，不是当前系统兼容性验证。
- RS232 分支只有安装程序，未对其内部二进制内容作 SDK 或行为推断。

ZIP 原始成员名称经其 CP437 表示还原为 GBK；RAR4 中文名称同时保存了原始名称字节与解码结果。Windows `tar` 对 CAN RAR 直接列表时会选择其中嵌入的 ZIP，因此另外核对了外层 RAR 文件头，再查阅所选嵌套归档，避免把内层 CP210x 文件误当作外层完整列表。

### ZIP 与嵌套 RAR 清单

```text
仿人五指灵巧手-驱动程序/
  USB转CAN通讯驱动(win).rar
    USB-CAN V2/
      EmbededConfig.exe
      EmbededDebug v2.0.rar
        data.mdb
        EmbededDebug v2.0.exe
      EmbededDebuggerV2.0使用说明.pdf
      USB-CAN V2用户手册.pdf
      USB-CAN用户编程说明及通讯库源文件.rar
        USB-CAN通讯模块用户编程说明及通讯库源文件/
          RT_CAN.cpp
          RT_CAN.h
          RT_COM.cpp
          RT_COM.h
          USB-CAN通讯模块用户编程说明.doc
      驱动程序.zip
  USB转RS232通讯驱动(win).rar
    CDM21216_Setup(usb转RS232  win10 driver).exe
  USB转RS485通讯驱动.rar
    USB转RS485通信驱动/
      CH341SER.ZIP
      CH341SER_LINUX.ZIP
```

`驱动程序.zip` 的完整文件清单（目录条目合并到树中）：

```text
CP210x_VCP_Windows/
  CP210xVCPInstaller_x64.exe
  CP210xVCPInstaller_x86.exe
  dpinst.xml
  ReleaseNotes.txt
  slabvcp.cat
  slabvcp.inf
  SLAB_License_Agreement_VCP_Windows.txt
  x64/
    silabenm.sys
    silabser.sys
    WdfCoInstaller01009.dll
  x86/
    silabenm.sys
    silabser.sys
    WdfCoInstaller01009.dll
```

`CH341SER.ZIP` 与 `CH341SER_LINUX.ZIP` 的完整文件清单：

```text
CH341SER/
  CH341PT.DLL
  CH341S64.SYS
  CH341S98.SYS
  CH341SER.CAT
  CH341SER.INF
  CH341SER.SYS
  CH341SER.VXD
  DRVSETUP64/DRVSETUP64.exe
  SETUP.EXE
  WIN 1X/
    CH341PT.DLL
    CH341S64.SYS
    CH341S98.SYS
    CH341SER.CAT
    CH341SER.INF
    CH341SER.SYS
    CH341SER.VXD
CH341SER_LINUX/
  ch34x.c
  Makefile
  readme.txt
```

## 手册与本地 SDK 的核对结论

下表定位采用手册印刷页码；PDF 实际页码比印刷页码多 3。复核了相关完整页面的文本及渲染图。寄存器与协议事实来自[官方 V1.09 手册](https://www.inspire-robots.com/d/file/p/2023/11-17/%E5%9B%A0%E6%97%B6%E6%9C%BA%E5%99%A8%E4%BA%BA%E4%BB%BF%E4%BA%BA%E4%BA%94%E6%8C%87%E7%81%B5%E5%B7%A7%E6%89%8B--RH56%E7%94%A8%E6%88%B7%E6%89%8B%E5%86%8CV1.09cn%20.pdf)；处理建议为本次代码审阅判断。

| 项目 | 官方证据 | SDK 处理原则 |
| --- | --- | --- |
| 私有串口帧 | §2.2，印刷页 4–9；8N1，默认 115200；长度以字节计；short 低字节在前 | 本地帧格式、字节长度和小端序一致；不混用 Modbus 字序或 CAN 适配器封包 |
| 电压 | 印刷页 11；1472/`0x05C0`，1 short，只读 | `REG_VOLTAGE=1472` 正确；只报告原始整数，手册未给出换算比例或电压寄存器单位 |
| 写 ACK | 印刷页 7；9 字节，命令 `0x12`，回显地址，结果 `1` | 校验帧、ID、地址、校验和和结果；ACK 不表示手指已到位 |
| SAVE | 印刷页 7–8；初始 ACK 后约 1 秒再发结果帧；`0x00` 成功，`0xFF` 失败 | 普通 ACK 解析不能直接处理保存结果；省略结果等待时不能声称 Flash 保存已确认 |
| HAND_ID | 印刷页 13；1–254，默认 1 | 设备配置与 CLI 使用 1–254；线上的 8 位字段宽度不能证明 0、255 是合法手 ID |
| 波特率 | 印刷页 13；寄存器值 0/1/2 对应 115200/57600/19200 | 校验实际波特率；不把寄存器编码误当作主机 baud |
| 角度保持 | 印刷页 16；1486 起，六个 short；`-1` 或 0–1000；§2.2 支持连续寄存器读写 | 手册描述 `-1`（线上 `FFFF`）为保持当前实际位置不动作；当前明确角度命令不开放该哨兵值。单指 CLI 只写所选通道的 2 字节寄存器，保留其他通道原目标；已在 COM13 验证食指地址 1492 的独立写入 |
| 速度 | 印刷页 18–19；1522 起，范围 0–1000；只解释 1000 的空载运动时间 | 0 可作为范围内设置值；手册未单独规定 0 的急停效果，不应把零速 ACK 描述为经过验证的急停 |
| 实际力 | 印刷页 20；1582 起，六个 short，g，表列范围 0–1000 | 保留本地有符号 16 位解码作为兼容处理；手册未解释负值物理含义，不能宣称负力范围获官方证实 |
| ERROR | 印刷页 20–21；1606 起，六个 byte；Bit0–4 为堵转/过温/过流/电机异常/通讯故障 | 本地位图一致；保留原始值，未知位不应消失 |
| STATUS | 印刷页 21–22；1612 起，六个 byte；0/1/2/3/5/6/7 | 本地映射一致：松开、抓取、位置到位、力控到位、电流保护、堵转、故障；未知码保留并标记诊断警告。本次设备初始返回 255，手册没有定义其含义 |
| 清错 | 印刷页 13；1004 写 1；过温不能强制清除 | 清错后的实际 ERROR/STATUS 才能反映恢复情况；过温在温度回落后自动清除 |
| 力校准 | 印刷页 13；1009 写 1，约 6 秒，自行执行张开/弯曲动作，必须空载 | 校验等待时间不能短于手册过程；8 秒属于软件余量，不能作为厂商规定；计时结束本身不是传感器校准成功的证明 |
| 旧寄存器常量 | 印刷页 11；1008 标为保留；未列 1066 的用户手势角度组 | `REG_GESTURE_NO_SET`、`REG_USER_DEF_ANGLE` 只能视为旧版兼容常量；本次 CLI 不据此开放操作 |
| 拇指限制 | 印刷页 16 的 ANGLE_SET 六通道均为 `-1`、0–1000 | 项目的 200 下限、700 保守上限及 900 旋转预设属于软件策略；不能标为 V1.09 厂商完整范围 |

运动完成需按 ANGLE_ACT/STATUS 等反馈判断，并考虑力控阈值可能先于角度目标停止。离线 Mock、帧测试与文档核查不替代真实硬件验证。

## CLI 复用选择

已检查本地驱动、协议、配置与常量，并查阅官方 CLI/解析器文档。此任务不需要下载或运行其他厂商 CLI，也未声称完成 PyPI/GitHub 全量实现检索。

| 候选 | 适配判断 |
| --- | --- |
| [Python argparse](https://docs.python.org/3.10/library/argparse.html) | 标准库已有子命令、类型转换和自动帮助；足够覆盖有限命令集合；推荐作为 SDK 上的薄层，无新增运行依赖 |
| [Click](https://click.palletsprojects.com/en/stable/) | 支持组合命令，需新增依赖；本次需求没有必须引入它的解析需求 |
| [Typer](https://typer.tiangolo.com/) | 基于类型注解构建 CLI，需新增框架依赖；本次不需要它提供的额外功能 |

参考 [Wuji CLI 官方 Introduction](https://docs.wuji.tech/docs/en/wuji-cli/latest/introduction/) 的命令组织、单次连接生命周期、JSON 输出及可脚本化退出码；借鉴交互约定，不复用其设备协议。建议：

- `ports` 列出主机串口；`ping` 通过一次只读 RH56 反馈确认当前指定端口和 ID；不把串口列表当作已发现 RH56 设备。
- `get`、`set`、`open`、`close` 等调用已有 SDK；每个命令连接、操作、关闭连接，CLI 不另写寄存器帧逻辑。
- 默认可读输出，提供 `--json`；成功数据写 stdout，错误写 stderr；成功为 0，参数错误为 2，设备/通信故障为非零。运行时错误不应带未处理的 traceback。
- 校准等会自动运动的命令使用明确的非交互确认参数。确认的是动作条件，不是固定等待时间能够保证校准成功。
- 六通道顺序始终为小指、无名指、中指、食指、拇指弯曲、拇指旋转；Mock 模式仅供离线演示与测试。

这些是本项目的设计建议。Wuji 的只读占用回退、USB/UDP 自动发现、升级机制依赖其自身设备能力，本次没有证据把这些行为移植为 RH56 功能。
