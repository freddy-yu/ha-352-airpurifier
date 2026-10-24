# 352 Air Purifier for Home Assistant

![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)
![IoT Class](https://img.shields.io/badge/IoT_Class-Local_Push-success.svg)

专为 352 品牌智能空气净化器打造的 Home Assistant 局域网本地集成插件。
**脱离云端，毫秒级响应，完全本地局域网 UDP 控制！**

## ✨ 支持的型号 (Supported Models)

- **352 X50S** — `F0 72` 帧，**已真机验证**（开关机/风速/模式/灯光/童锁全生效）
- 352 X83 / X83C — `A5 A0` 帧，沿用原实现
- 352 X50（老固件）— `A5 A0` 帧，沿用原实现
- 352 X60 / X70 / G30 — 与 X50S 同族，未经实测

> X50 与 X50S 协议层设备类型相同（`0x03`），差别在内层帧：
> 老固件 `A5 A0` + 单字节累加和，新固件 `F0 72` + CRC16。
> **X50 控制无反应时请改选 X50S。**

### X50S 实测要点

- ✅ 开关机、风速 1–5 档、模式、灯光、童锁 全部生效
- ✅ 认证码自动学习有效
- ⚠️ 设备**不回应 IPv4 广播，只回应单播**（集成已双发）
- ⚠️ 定时命令 `0x54` 无响应，X50S 不支持
- ⚠️ 无温湿度/CO₂ 传感器（上报恒为 0）
- ℹ️ 手动模式为 `raw=4`；极速模式会跑到 6 档（超出 5 档属正常）

## 🚀 核心特性 (Features)

- ⚡ **完全本地化**：不依赖 352 官方云服务器，断网依然可用
- 🔄 **状态即时同步**：UDP 直连，设备状态变化主动推送
- 🛡️ **命令不乐观锁**：设备上报即真相，避免状态永久错误
- 🌬️ **风机控制**：开关机、1–5 档风速调节（X50S）
- 🎛️ **模式切换**：自动 / 睡眠 / 极速 / 手动
- 💡 **灯光控制**：屏幕灯光开关
- 📊 **传感器**：PM2.5、累计净化量、滤芯状态
- 🔑 **认证码自动学习**：从设备回帧包头提取，无需手工填写

## 📦 安装方法 (Installation)

### 推荐方法：通过 HACS 安装

1. 打开 Home Assistant，进入 HACS
2. 点击右上角的三个点 `...` → **自定义存储库 (Custom repositories)**
3. 存储库 URL 填入：`https://github.com/freddy-yu/ha-352-airpurifier`
4. 类别选择：**集成 (Integration)**
5. 点击添加后，在 HACS 中搜索 `352 Air Purifier` 并下载安装
6. 重启 Home Assistant

### 手动安装

1. 下载本仓库代码
2. 把 `custom_components/air_352_x83` 文件夹放入 HA 根目录的 `custom_components` 中
3. 重启 Home Assistant

## ⚙️ 配置使用 (Configuration)

1. 在 HA 左侧菜单点击 **配置** → **设备与服务**
2. 点击右下角 **添加集成**，搜索 `352`
3. 在弹出配置框中输入：

   - **型号**：X50S 请选择 `352 X50S 空气净化器`
   - **设备 IP**：净化器在局域网内的 IP（建议绑定静态 IP）
   - **MAC 地址**：设备 MAC，格式如 `00:95:69:D7:9B:FE`
   - **认证码**（可选）：形如 `22B5` 的十六进制值，留空则自动学习

4. 提交后即可自动生成风机、屏幕灯和多个传感器实体

### 端口说明

集成会尝试监听 UDP `11530`。若该端口被 352 官方 App 占用会自动改用临时端口，
此时设备应答仍可收到，但主动广播可能丢失。建议关闭手机上的 352 App 后重启集成。

## 🧪 离线验证

`protocol.py` 是纯 Python、不依赖 HA，可直接跑自测：

```bash
python tests/test_protocol.py
python tests/test_hub.py
```

## 📝 已知限制

- X60 / X70 / G30 按同族协议实现，未经真机验证
- 定时开关机组、童锁、PTC 命令已定义但尚未做成实体
- 滤芯写入（SN 码）未实现

## 📬 贡献与支持

本项目基于对 352 官方 App 的逆向分析开发。
如果你有其他型号设备（如 G30 新风、净水器等），欢迎提交 Issue 或 PR 共同完善！
