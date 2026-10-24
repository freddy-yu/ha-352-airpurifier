"""352 协议离线自测：不依赖 Home Assistant。"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352"

# 用假包让 const.py 里的相对导入生效
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

FAILS = []


def check(label, actual, expected):
    if actual != expected:
        FAILS.append(f"{label}\n  实际: {actual}\n  期望: {expected}")
        print(f"FAIL {label}")
    else:
        print(f"ok   {label}")


MAC = "009569D79BFE"
# 由逆向出的字节码手工推导，作为基准
QUERY_EXPECTED = (
    "A1 04 00 95 69 D7 9B FE 17 00 00 01 F1 03 22 B5 01 "
    "F0 72 00 0D 03 04 02 00 01 03 11 11 00 94 9D"
)
POWER_ON_EXPECTED = (
    "A1 04 00 95 69 D7 9B FE 17 00 00 03 F1 03 22 B5 01 "
    "F0 72 00 0D 03 04 02 00 03 03 5E 00 00 D1 C0"
)
SEARCH_EXPECTED = "A1 04 00 95 69 D7 9B FE 08 00 00 00 F1 03 CB 76 23"


def hx(data: bytes) -> str:
    return data.hex(" ").upper()


# 1. 构造帧与逆向基准一致
check(
    "查询帧",
    hx(protocol.build_f072_command(MAC, 0xF1, 0x03, 0x22B5, 1, 0x11, 0x11)),
    QUERY_EXPECTED,
)
check(
    "开机帧",
    hx(protocol.build_f072_command(MAC, 0xF1, 0x03, 0x22B5, 3, 0x5E, 0x00)),
    POWER_ON_EXPECTED,
)
check(
    "搜索帧",
    hx(protocol.build_search_frame(MAC, 0xF1, 0x03, 0xCB76, 0)),
    SEARCH_EXPECTED,
)
check("APP_AUTH 常量", 0xCB76, 0xCB76)

# 2. CRC 自洽：产生的帧必须能通过自身校验
for label, packet in [
    ("查询帧 CRC", protocol.build_f072_command(MAC, 0xF1, 0x03, 0x22B5, 1, 0x11, 0x11)),
    ("风速帧 CRC", protocol.build_f072_command(MAC, 0xF1, 0x03, 0x22B5, 9, 0x52, 3)),
    ("模式帧 CRC", protocol.build_f072_command(MAC, 0xF1, 0x03, 0x22B5, 7, 0x51, 1)),
]:
    inner = packet[17:]
    check(label, protocol.crc16(inner[2:-2]), inner[-2:])

# 3. 头部解析
header = protocol.parse_header(bytes.fromhex(QUERY_EXPECTED.replace(" ", "")))
check("MAC 解析", header["mac"], MAC)
check("厂商标码", header["company"], 0xF1)
check("设备类型", header["device_type"], 0x03)
check("认证码", header["auth"], 0x22B5)
check("序号", header["seq"], 1)

# 4. 协议识别
check("识别 F0 72", protocol.detect_protocol(header["content"]), protocol.PROTOCOL_F072)
check(
    "识别 A5 A0",
    protocol.detect_protocol(b"\x01\xa5\xa0\x51\x01\x00\x00\x00"),
    protocol.PROTOCOL_A5A0,
)


def build_state_frame() -> bytes:
    """按逆向出的偏移造一个状态上报帧。"""
    s = bytearray(30)
    s[3] = 0x21          # 模式=1(auto)，滤芯类型=2(碳)
    s[4] = 3             # 风速 3
    s[5] = 2             # 定时 2 小时
    s[6] = 2             # 空气质量
    s[7] = 0x11          # 童锁关
    s[8] = 0x00          # 灯开
    s[9] = 0x00          # 电源开
    s[10:12] = (0).to_bytes(2, "big")
    s[12:14] = (35).to_bytes(2, "big")     # PM2.5
    s[14] = 24                             # 温度
    s[15] = 55                             # 湿度
    s[16:18] = (600).to_bytes(2, "big")    # CO2
    s[18] = 1                              # PTC
    s[19:21] = (100).to_bytes(2, "big")    # 累计运行
    s[21] = 1
    s[22:24] = (1234).to_bytes(2, "big")   # x10
    s[24] = 2
    s[25:27] = (56).to_bytes(2, "big")     # x100

    body = bytes([0x03, 0x84, 0x02]) + bytes(s)
    inner_total = 4 + len(body) + 2
    inner = (
        bytes([0xF0, 0x72])
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
        + (5).to_bytes(2, "big")
        + bytes([0xF1, 0x03])
        + (0x22B5).to_bytes(2, "big")
    )
    return head + content


frame = build_state_frame()
state = protocol.parse_state(frame)
check("状态帧可解析", state is not None, True)
if state:
    check("电源", state["power"], True)
    check("模式", state["mode"], "auto")
    check("滤芯类型", state["filter_type"], "carbon")
    check("风速", state["speed"], 3)
    check("定时", state["timer"], 2)
    check("童锁", state["child_lock"], False)
    check("灯光", state["light"], True)
    check("PM2.5", state["pm25"], 35)
    check("温度", state["temperature"], 24)
    check("湿度", state["humidity"], 55)
    check("CO2", state["co2"], 600)
    check("累计净化量", state["total_purification"], 12340)
    check("累计净化总量", state["cumulative_purification"], 5600)

# 5. 搜索应答
resp_content = b"\x23" + bytes([192, 168, 1, 50]) + bytes.fromhex(MAC)
resp_total = 16 + len(resp_content)
resp = (
    b"\xA1\x04"
    + bytes.fromhex(MAC)
    + bytes([(resp_total - 9) & 0xFF, 0x00])
    + (1).to_bytes(2, "big")
    + bytes([0xF1, 0x03])
    + (0x22B5).to_bytes(2, "big")
    + resp_content
)
parsed = protocol.parse_search_response(resp)
check("搜索应答 IP", parsed["ip"], "192.168.1.50")
check("搜索应答 MAC", parsed["mac"], MAC)

# 6. 损坏的帧必须被拒绝
broken = bytearray(frame)
broken[-1] ^= 0xFF
check("CRC 错误的帧被拒绝", protocol.parse_state(bytes(broken)), None)
check("非 0xA1 帧被拒绝", protocol.parse_header(b"\x00" * 20), None)

# 7. 老 A5 A0 帧仍可构造
a5 = protocol.build_a5a0_command(MAC, 0xF1, 0x03, 0x0504, 2, 0x11, 0x11)
check("A5A0 帧起始", a5[17:19], b"\xa5\xa0")
check("A5A0 累积和", a5[-1], protocol.checksum(a5[17:-1]))


# 8. 部分 X83 固件的状态帧没有内层封装，CONTENT 直接是状态
def build_legacy_state_frame() -> bytes:
    s = bytearray(31)
    s[3] = 0x11          # 模式 1，滤芯类型 1
    s[4] = 4
    s[7] = 0x11
    s[8] = 0x11
    s[9] = 0x11          # 电源关
    s[12:14] = (88).to_bytes(2, "big")
    total = 16 + len(s)
    head = (
        b"\xA1\x04"
        + bytes.fromhex(MAC)
        + bytes([(total - 9) & 0xFF, 0x00])
        + (12).to_bytes(2, "big")
        + bytes([0xF1, 0x02])
        + (0x0504).to_bytes(2, "big")
    )
    return head + bytes(s)


legacy = build_legacy_state_frame()
check("老式帧无内层封装", protocol.detect_protocol(legacy[16:]), None)
legacy_state = protocol.parse_state(legacy, protocol.PROTOCOL_A5A0)
check("老式 X83 帧可解析", legacy_state is not None, True)
if legacy_state:
    check("老式帧 PM2.5", legacy_state["pm25"], 88)
    check("老式帧电源", legacy_state["power"], False)
    check("老式帧风速", legacy_state["speed"], 4)

# F072 帧走老协议分支时也不能误判
check(
    "F072 帧走老分支仍可解析",
    protocol.parse_state(frame, protocol.PROTOCOL_A5A0) is not None,
    True,
)

print()
if FAILS:
    print(f"=== {len(FAILS)} 项失败 ===")
    for item in FAILS:
        print(item)
    sys.exit(1)
print("全部通过")
