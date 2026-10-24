# 352 X50S Air Purifier for Home Assistant

为 **352 X50S** 打造的 Home Assistant 本地局域网集成，无需云端，UDP 直连。

> 基于 [yymonday/ha-352-airpurifier](https://github.com/yymonday/ha-352-airpurifier)（作者 [@yymonday](https://github.com/yymonday)）。
> 原始协议逆向与 X83/X50 支持归原作者。本 fork 由 [@freddy-yu](https://github.com/freddy-yu) 维护，
> 新增功能均在真实 X50S 上验证。包名 `air_352_x50s`（上游为 `air_352_x83`）。

## 功能

- 开关机
- 四种运行模式：自动 / 睡眠 / 极速 / 手动
- 风速 1–5 档
- 屏幕灯开关
- 童锁开关
- 传感器：PM2.5、当前风速、累计净化量、滤芯状态
- 状态变化主动推送

## 相对上游的改动

- 新增 `F0 72` 协议层（CRC16 新帧格式），上游只有老式 `A5 A0`
- 双协议按型号自动选择
- 认证码自动学习，无需手填
- 修复：命令后锁状态会丢弃设备真实的关机/调速回帧
- 修复：X50S 不回应广播，改为广播 + 单播双发
- 修复：手动模式取值应为 `0x04`（`0x05` 无响应）
- 新增模式 / 档位 `select` 实体（风扇卡片默认不显示下拉框和滑块）

## 支持型号

| 型号 | 协议 | 状态 |
|---|---|---|
| **352 X50S** | `F0 72` | **已真机验证** |
| 352 X50 / X83 / X83C | `A5 A0` | 沿用上游，未实测 |
| 352 X60 / X70 / G30 | `F0 72` | 按同族实现，未实测 |

## 安装

**HACS**：自定义存储库添加 `https://github.com/freddy-yu/ha-352-x50s-airpurifier`，
类别选「集成」，搜索 `352 X50S` 安装，重启 HA。

**手动**：把 `custom_components/air_352_x50s` 复制到 HA 配置目录的 `custom_components/` 下，重启。

> 升级注意：删掉旧集成条目和旧目录（`air_352_x83` 或 `air_352`），
> 只保留 `air_352_x50s`，否则 domain 冲突。

## 配置

设置 → 设备与服务 → 添加集成 → 搜索 `352`：

- 型号：X50S
- IP 地址：设备局域网 IP
- MAC 地址：如 `F0:FE:6B:93:88:FF`
- 认证码：可留空，自动学习

## 使用说明

**模式与档位**用 `select.运行模式` 和 `select.风速档位`。也可以编辑风扇卡片 →
添加功能 → 勾选「Preset modes」和「Speed」。

**档位由谁决定**：设备只上报当前风速。自动模式按空气质量自己调（常停在 1 档），
睡眠固定 1 档，极速跑到 6 档，只有手动模式才是你设定的档位。

**累计净化量**：设备运行时才增长（约 200–300 m³/h）。基数几十万，
短时间内看不出变化属正常。

**关机时**：灯光命令被忽略，灯实体显示不可用。模式和档位命令会自动先开机再执行。

**端口**：监听 UDP `11530`，被 352 App 占用时自动降级到临时端口。

## 已知限制

- 定时开关机、PTC 在 X50S 上无响应，未实现
- 滤芯 SN 写入未实现
- X60 / X70 / G30 / X83 未经真机验证

## 开发

`protocol.py` 纯 Python 无 HA 依赖，可离线验证：

```bash
python tests/test_protocol.py
python tests/test_hub.py
python tests/test_entity.py
python tests/test_select.py
python tests/test_sensor.py
```

协议细节见 [`docs/X50S-协议逆向笔记.md`](docs/X50S-协议逆向笔记.md)。
