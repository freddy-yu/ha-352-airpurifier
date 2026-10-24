"""Hub 层离线自测：模拟设备帧，验证状态解析与身份学习。"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352_x50s"

pkg = types.ModuleType("air352")
pkg.__path__ = [str(COMP_DIR)]
sys.modules["air352"] = pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"air352.{name}", COMP_DIR / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"air352.{name}"] = module
    spec.loader.exec_module(module)
    return module


protocol = _load("protocol")
const = _load("const")
hub_mod = _load("hub")

FAILS = []
MAC = "009569D79BFE"


def check(label, actual, expected):
    if actual != expected:
        FAILS.append(f"{label}: 实际 {actual!r} 期望 {expected!r}")
        print(f"FAIL {label}")
    else:
        print(f"ok   {label}")


def build_state_frame(auth=0x22B5, power_on=True, speed=3, mode=1, pm25=35, seq=5):
    s = bytearray(30)
    s[3] = ((2 << 4) | mode) & 0xFF
    s[4] = speed
    s[5] = 0
    s[6] = 2
    s[7] = 0x11
    s[8] = 0x00
    s[9] = 0x00 if power_on else 0x11
    s[10:12] = (0).to_bytes(2, "big")
    s[12:14] = pm25.to_bytes(2, "big")
    s[14] = 24
    s[15] = 55
    s[16:18] = (600).to_bytes(2, "big")
    s[18] = 1
    s[19:21] = (100).to_bytes(2, "big")
    s[21] = 1
    s[22:24] = (1234).to_bytes(2, "big")
    s[24] = 2
    s[25:27] = (56).to_bytes(2, "big")

    body = bytes([0x03, 0x84, 0x02]) + bytes(s)
    inner_total = 4 + len(body) + 2
    inner = (
        protocol.STX_F072
        + (inner_total - 2).to_bytes(2, "big")
        + body
        + protocol.crc16((inner_total - 2).to_bytes(2, "big") + body)
    )
    content = b"\x01" + inner
    total = 16 + len(content)
    head = (
        b"\xA1\x04"
        + bytes.fromhex(MAC)
        + bytes([(total - 9) & 0xFF, 0x00])
        + seq.to_bytes(2, "big")
        + bytes([0xF1, 0x03])
        + auth.to_bytes(2, "big")
    )
    return head + content


hub = hub_mod.Air352Hub(None, "192.168.1.50", MAC, "x50s")

# 1. 状态帧解析
ok = hub.parse_data(build_state_frame())
check("帧被接受", ok, True)
check("电源", hub.status["power"], True)
check("风速", hub.status["speed"], 3)
check("模式", hub.status["mode"], "auto")
check("PM2.5", hub.status["pm25"], 35)
check("滤芯类型", hub.status["filter_type"], "carbon")
check("温度", hub.status["temperature"], 24)
check("CO2", hub.status["co2"], 600)
check("累计净化量", hub.status["total_purification"], 12340)
check("在线", hub.available, True)

# 2. 关机帧
hub.parse_data(build_state_frame(power_on=False, seq=6))
check("关机状态", hub.status["power"], False)

# 3. 认证码学习（非 APP 码）
hub2 = hub_mod.Air352Hub(None, "", MAC, "x50s")
check("初始 auth 为默认值", hub2.auth, const.DEFAULT_DEVICE_AUTH)
hub2.parse_data(build_state_frame(auth=0x1234))
check("学到真实 auth", hub2.auth, 0x1234)

# 4. 回显 APP 认证码时不学习
hub3 = hub_mod.Air352Hub(None, "", MAC, "x50s")
hub3.parse_data(build_state_frame(auth=const.APP_AUTH_CODE))
check("不把 APP 码当设备码", hub3.auth, const.DEFAULT_DEVICE_AUTH)

# 5. 显式配置 auth 后不覆盖
hub4 = hub_mod.Air352Hub(None, "", MAC, "x50s", auth=0x9999)
hub4.parse_data(build_state_frame(auth=0x1234))
check("显式配置优先", hub4.auth, 0x9999)

# 6. 别的设备的帧被忽略
hub5 = hub_mod.Air352Hub(None, "", "AABBCCDDEEFF", "x50s")
check("陌生 MAC 被忽略", hub5.parse_data(build_state_frame()), False)
check("陌生 MAC 不改状态", hub5.status["pm25"], 0)

# 7. 命令构造：发出去的帧能被自己解析回头部
hub6 = hub_mod.Air352Hub(None, "192.168.1.50", MAC, "x50s", auth=0x22B5)
packet = hub6._build_command(0x5E, 0x00)
header = protocol.parse_header(packet)
check("命令帧 MAC", header["mac"], MAC)
check("命令帧类型", header["device_type"], 0x03)
check("命令帧 auth", header["auth"], 0x22B5)
check("命令帧序号递增", header["seq"], 1)
check("命令帧内层", header["content"][1:3], protocol.STX_F072)
check("命令帧 CRC", protocol.crc16(packet[19:-2]), packet[-2:])

# 8. 未知命令被拒绝
import asyncio  # noqa: E402

result = asyncio.run(hub6.async_control("not_a_command"))
check("未知命令返回 False", result, False)

# 9. 模型参数
check("X50S 档数", const.model_info("x50s")["speed_count"], 5)
check("X83 档数", const.model_info("x83")["speed_count"], 6)
check("X50S 协议", const.model_info("x50s")["protocol"], protocol.PROTOCOL_F072)
check("X50 协议", const.model_info("x50")["protocol"], protocol.PROTOCOL_A5A0)
check("X83 协议", const.model_info("x83")["protocol"], protocol.PROTOCOL_A5A0)
check("X50S 设备类型", const.model_info("x50s")["device_type"], 0x03)

print()
if FAILS:
    print(f"=== {len(FAILS)} 项失败 ===")
    for item in FAILS:
        print(item)
    sys.exit(1)
print("全部通过")
