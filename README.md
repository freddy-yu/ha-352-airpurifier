# 352 X50S Air Purifier for Home Assistant

为 **352 X50S** 打造的 Home Assistant 本地局域网集成，无需云端。

> 基于 [yymonday/ha-352-airpurifier](https://github.com/yymonday/ha-352-airpurifier)（作者 [@yymonday](https://github.com/yymonday)）。
> 原始协议逆向与 X83/X50 支持归原作者。本 fork 由 [@freddy-yu](https://github.com/freddy-yu) 维护，
> 新增功能均在真实 X50S 上逐项验证。

## 功能

- **开关机**
- **四种运行模式**：自动 / 睡眠 / 极速 / 手动
- **风速 1–5 档**（手动模式下可调）
- **屏幕灯**开关
- **童锁**开关
- **传感器**：PM2.5、当前风速、累计净化量、滤芯状态
- 设备状态变化主动推送，无需轮询

## 相对上游的改动

| 改动 | 说明 |
|---|---|
| 新增 `F0 72` 协议层 | X50S 用新帧格式（CRC16），上游只实现了老式 `A5 A0` 帧 |
| 双协议通信 | 按型号自动选择帧格式 |
| 认证码自动学习 | 从设备回帧提取，无需手工填写 |
| 修复状态丢失 | 上游命令后锁 3 秒会永久丢弃设备真实的关机/调速回帧 |
| 修复设备发现 | X50S 不回应 IPv4 广播，改为广播 + 单播双发 |
| 修复手动模式取值 | `0x05` 改为 `0x04`，`0x05` 在 X50S 上无响应 |
| 新增模式/档位选择实体 | HA 风扇卡片默认不显示下拉框和滑块，用 `select` 实体补足 |

## 支持型号

| 型号 | 协议 | 状态 |
|---|---|---|
| **352 X50S** | `F0 72` | **已真机验证** |
| 352 X50 / X83 / X83C | `A5 A0` | 沿用上游，未实测 |
| 352 X60 / X70 / G30 | `F0 72` | 按同族实现，未实测 |

## 安装

**HACS**：HACS → 自定义存储库 → 添加 `https://github.com/freddy-yu/ha-352-airpurifier`
（类别选「集成」）→ 搜索 `352 X50S` 安装 → 重启 HA

**手动**：把 `custom_components/air_352_x50s` 复制到 HA 配置目录的 `custom_components/` 下，重启。

> **升级注意**：包名变更过。删掉旧集成条目和旧目录
> （`air_352_x83` 或 `air_352`），只保留 `air_352_x50s`，否则 domain 冲突。

## 配置

设置 → 设备与服务 → 添加集成 → 搜索 `352`，填写：

- **型号**：选 X50S
- **IP 地址**：设备的局域网 IP（建议在路由器绑定静态 IP）
- **MAC 地址**：格式 `F0:FE:6B:93:88:FF`
- **认证码**（可选）：留空自动学习

## 实体

| 实体 | 说明 |
|---|---|
| `fan` | 主控：开关、风速、模式 |
| `select.运行模式` | 自动 / 睡眠 / 极速 / 手动 |
| `select.风速档位` | 1–5 档 |
| `light` | 屏幕灯（设备关机时不可用） |
| `sensor.pm25` | PM2.5 |
| `sensor.speed` | 当前风速档位 |
| `sensor.cumulative_purification` | 累计净化量 (m³) |
| `sensor.filter_type` | 滤芯状态 |

## 使用说明

**模式与档位**：`select.运行模式` 和 `select.风速档位` 是最直接的入口。
也可以编辑风扇卡片 → 添加功能 → 勾选「Preset modes」和「Speed」。

**档位由谁决定**：设备只上报「当前风速」，不区分设定值和实际值。

- 自动模式：设备按空气质量自己调，空气好时停在 1 档
- 睡眠模式：固定 1 档
- 极速模式：跑到 6 档（超出可选范围，此时档位实体显示未知）
- 手动模式：你选几档就是几档

想让档位保持你设定的值，请用**手动模式**。

**累计净化量**：设备运行时才增长，速度约 200–300 m³/h。
基数是几十万，所以短时间内看不出变化是正常的。

**关机时**：灯光命令会被忽略，所以灯实体显示为不可用。
模式和档位命令也会被忽略，但集成会自动先开机再执行。

**端口**：集成监听 UDP `11530`。若被手机上的 352 App 占用会自动降级到临时端口，
建议关闭手机 App 后重启集成。

## 已知限制

- 定时开关机、PTC 在 X50S 上无响应，未实现
- 滤芯 SN 写入未实现
- X60 / X70 / G30 / X83 未经真机验证

## 开发

`protocol.py` 是纯 Python、不依赖 HA，可离线验证：

```bash
python tests/test_protocol.py   # 帧构造 / CRC / 解析
python tests/test_hub.py        # 认证码学习 / 状态合并
python tests/test_entity.py     # fan / light 命令序列
python tests/test_select.py     # 模式 / 档位实体
python tests/test_sensor.py     # 传感器取值
```

真机测试（需设备在网）：

```bash
python tests/probe_device.py 192.168.0.29   # 只读诊断
python tests/probe_verify.py                # 逐条命令查询确认
python tests/test_live_entity.py            # 端到端
python tests/test_live_select.py
```

协议逆向细节（帧结构、CRC、字段偏移）见 [`docs/X50S-协议逆向笔记.md`](docs/X50S-协议逆向笔记.md)。
