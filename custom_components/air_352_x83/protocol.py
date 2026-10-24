"""352 空气净化器局域网协议编解码。

逆向自 352 官方 App (`com.bugull.threefivetwoaircleaner`)：

  外层头 16 字节
  ---------------------------------------------------------------
  0    0xA1            协议版本
  1    0x04            地址类型/标志位
  2..7 MAC             设备 MAC，正常字节序
  8    LEN             总长度 - 9
  9    保留
  10..11  SEQ          包序号，大端，0..32767 循环
  12   COMPANY         厂商码 0xF1=LRD 0xF2=HF
  13   DEVICE_TYPE     2=X83 3=X50/X50S/X60/X70 4=G30
  14..15 AUTH          认证码，大端
  16.. CONTENT         命令内容

CONTENT 有两种：
  * ``[channel][内层帧]`` —— channel 由设备类型决定（1->0x03，2/3/4->0x01，其它->0x00）
  * ``[cmd][参数...]``    —— 搜索/心跳/订阅等

内层帧 ``F0 72``（X50S 等新固件）：
  ---------------------------------------------------------------
  0    0xF0
  1    0x72
  2..3 LEN             内层长度 - 2，大端
  4    DEVICE_TYPE
  5    0x04            固定
  6    CMD             0x02=控制/查询，应答时置 0x84
  7..8 SEQ
  9    SUB             数据长度
  10.. 参数
  末2  CRC16           覆盖 [2 .. len-3]，poly 0x1021，init 0xFFFF，
                       初值 MSB-first，结果取反
"""

from __future__ import annotations

PROTOCOL_A5A0 = "a5a0"
PROTOCOL_F072 = "f072"

VERSION = 0xA1
FLAGS = 0x04

# 内层帧起始标记
STX_F072 = b"\xf0\x72"
STX_A5A0 = b"\xa5\xa0"

# 内层 CMD
CMD_CONTROL = 0x02
CMD_CONTROL_RESP = 0x84
CMD_SEARCH = 0x23
CMD_HEARTBEAT = 0x61
CMD_QUERY_DEVICE_INFO = 0x62
CMD_LOCK = 0x24
CMD_RESET = 0x43

# 应答帧业务子命令（CONTENT[6] == 0x84 时）
SUB_FILTER_INFO = 0x03
SUB_TIMER_GROUP = 0x04
SUB_FILTER_WARNING = 0x06


def crc16(data: bytes) -> bytes:
    """352 私有 CRC16：poly 0x1021 / init 0xFFFF / MSB-first / 结果取反。"""
    crc = 0xFFFF
    for byte in data:
        for i in range(8):
            msb = (crc & 0x8000) >> 8
            bit = (byte << i) & 0x80
            crc = (crc << 1) & 0xFFFF
            if msb ^ bit:
                crc ^= 0x1021
    crc = (~crc) & 0xFFFF
    return bytes([crc >> 8, crc & 0xFF])


def checksum(data: bytes) -> int:
    """老 A5 A0 帧用的单字节累加和。"""
    return sum(data) & 0xFF


def mac_to_bytes(mac: str) -> bytes:
    clean = mac.replace(":", "").replace("-", "").replace(" ", "").upper()
    if len(clean) != 12:
        raise ValueError(f"invalid MAC: {mac!r}")
    return bytes.fromhex(clean)


def _be16(value: int) -> bytes:
    return bytes([(value >> 8) & 0xFF, value & 0xFF])


# --------------------------------------------------------------------------
# 构造
# --------------------------------------------------------------------------

def build_frame(
    mac: str,
    company: int,
    device_type: int,
    auth: int,
    seq: int,
    content: bytes,
) -> bytes:
    """套上 16 字节外层头。"""
    total = 16 + len(content)
    header = (
        bytes([VERSION, FLAGS])
        + mac_to_bytes(mac)
        + bytes([(total - 9) & 0xFF, 0x00])
        + _be16(seq)
        + bytes([company & 0xFF, device_type & 0xFF])
        + _be16(auth)
    )
    return header + content


def build_f072_inner(device_type: int, seq: int, p5: int, p6: int) -> bytes:
    """F0 72 控制帧：4 字节参数 [0x03, P5, P6, 0x00]。"""
    body = (
        bytes([device_type & 0xFF, 0x04, CMD_CONTROL])
        + _be16(seq)
        + bytes([0x03, p5 & 0xFF, p6 & 0xFF, 0x00])
    )
    total = 4 + len(body) + 2
    head = bytes([0xF0, 0x72]) + _be16(total - 2)
    return head + body + crc16(head[2:] + body)


def build_f072_command(
    mac: str,
    company: int,
    device_type: int,
    auth: int,
    seq: int,
    p5: int,
    p6: int,
) -> bytes:
    """X50S 等设备的完整控制帧（含通道字节）。"""
    inner = build_f072_inner(device_type, seq, p5, p6)
    channel = 1 if device_type in (2, 3, 4) else 0
    return build_frame(mac, company, device_type, auth, seq, bytes([channel]) + inner)


def build_a5a0_command(
    mac: str,
    company: int,
    device_type: int,
    auth: int,
    seq: int,
    p5: int,
    p6: int,
) -> bytes:
    """X83 等老固件的控制帧：A5 A0 + 单字节累加和，无通道字节。"""
    body = bytes([0xA5, 0xA0, p5 & 0xFF, p6 & 0xFF, 0x00, 0x00])
    inner = body + bytes([checksum(body)])
    channel = 1 if device_type in (2, 3, 4) else 0
    return build_frame(mac, company, device_type, auth, seq, bytes([channel]) + inner)


def build_search_frame(
    mac: str,
    company: int,
    device_type: int,
    auth: int,
    seq: int,
) -> bytes:
    """局域网搜索：CONTENT 只有 0x23 一个字节。"""
    return build_frame(mac, company, device_type, auth, seq, bytes([CMD_SEARCH]))


def build_heartbeat_frame(
    mac: str,
    company: int,
    device_type: int,
    auth: int,
    seq: int,
) -> bytes:
    return build_frame(mac, company, device_type, auth, seq, bytes([CMD_HEARTBEAT]))


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------

def parse_header(data: bytes) -> dict | None:
    """拆外层头；不是合法帧返回 None。"""
    if len(data) < 16 or data[0] != VERSION:
        return None
    return {
        "flags": data[1],
        "mac": data[2:8].hex().upper(),
        "length": data[8],
        "seq": (data[10] << 8) | data[11],
        "company": data[12],
        "device_type": data[13],
        "auth": (data[14] << 8) | data[15],
        "content": data[16:],
        "raw": data,
    }


def detect_protocol(content: bytes) -> str | None:
    """从 CONTENT 判断内层帧类型。"""
    if len(content) >= 3 and content[1:3] == STX_F072:
        return PROTOCOL_F072
    if len(content) >= 3 and content[1:3] == STX_A5A0:
        return PROTOCOL_A5A0
    return None


def _verify_crc16(data: bytes, inner_start: int = 17) -> bool:
    """内层帧末两字节是 CRC16，覆盖内层 [2 .. len-3]。

    ``inner_start`` 是 ``F0 72`` 在整帧里的下标（16 字节外层头 + 1 字节通道）。
    """
    inner = data[inner_start:]
    if len(inner) < 6:
        return False
    return crc16(inner[2:-2]) == inner[-2:]


# X50S 实测：raw=1 自动 / 2 睡眠 / 3 极速 / 4 手动；5 在 X50S 上无响应。
# App 的常量表把 5 当手动（适配老固件），这里两者都映射为 manual。
MODE_MAP = {1: "auto", 2: "sleep", 3: "turbo", 4: "manual", 5: "manual"}
FILTER_TYPE_MAP = {0: "none", 1: "standard", 2: "carbon"}


def parse_state(data: bytes, protocol: str = PROTOCOL_F072) -> dict | None:
    """解析状态上报帧。

    两种布局：

    * **F0 72 帧**（X50S 等新固件）：16 字节外层头 + 1 字节通道 + 8 字节内层头，
      状态数据从 offset 24 开始，末尾 2 字节是 CRC16。
    * **老式 A5 A0 设备的状态帧**（部分 X83 固件）：CONTENT 直接就是状态数据，
      状态从 offset 16 开始，末尾不是 CRC16，所以不校验。

    字段偏移与 App 的 ``AirCleaner50DataParser`` 逐项对应。
    """
    header = parse_header(data)
    if header is None:
        return None

    content = header["content"]
    if not content:
        return None

    is_f072 = len(content) >= 3 and content[1:3] == STX_F072
    if is_f072:
        # CONTENT = [channel][F0 72][len 2B][dev_type][0x84][0x02][...]
        # 应答帧的内层 CMD 位于 CONTENT[7]，CONTENT[6] 是应答标志 0x84
        if len(content) < 8 or content[7] != CMD_CONTROL:
            return None
        if not _verify_crc16(data):
            return None
        base = 24
    else:
        # 老式帧：没有内层封装，CONTENT 本身就是状态数据
        if protocol != PROTOCOL_A5A0:
            return None
        base = 16

    body = data[base:-2]
    if len(body) < 27:
        return None

    mode_raw = body[3] & 0x0F
    filter_raw = (body[3] >> 4) & 0x0F

    def be16(idx: int) -> int:
        if idx + 1 >= len(body):
            return 0
        return (body[idx] << 8) | body[idx + 1]

    def scaled(idx: int) -> int:
        """净化量：倍率字节 + 大端数值。"""
        if idx + 2 >= len(body):
            return 0
        exp = body[idx]
        factor = (10 ** exp) if exp in (0, 1, 2, 3) else 1
        return be16(idx + 1) * factor

    state = {
        "mode": MODE_MAP.get(mode_raw),
        "mode_raw": mode_raw,
        "filter_type": FILTER_TYPE_MAP.get(filter_raw, "none"),
        "filter_raw": filter_raw,
        "speed": body[4],
        "timer": body[5],
        "timer_hours": body[5],
        "air_quality": body[6],
        "child_lock": body[7] == 0x00,
        "light": body[8] == 0x00,
        "power": body[9] == 0x00,
        "last_timer": be16(10),
        "pm25": be16(12),
        "temperature": body[14],
        "humidity": body[15],
        "co2": be16(16),
        "ptc": body[18],
        "total_online_time": be16(19),
        "total_purification": scaled(21),
        "cumulative_purification": scaled(24),
        "online": True,
    }

    online = state["total_online_time"]
    if online > 65059 or (10000 < online < 65000):
        state["total_online_time"] = 0
    if state["total_purification"] >= 9999999:
        state["total_purification"] = 0
    if state["cumulative_purification"] >= 9999999:
        state["cumulative_purification"] = 0

    if len(body) > 29:
        state["linkage"] = body[29]

    return state


def parse_search_response(data: bytes) -> dict | None:
    """解析 0x23 搜索应答：CONTENT = [0x23][IP 4B][MAC 6B]。"""
    header = parse_header(data)
    if header is None:
        return None
    content = header["content"]
    if len(content) < 11 or content[0] != CMD_SEARCH:
        return None
    return {
        "ip": ".".join(str(b) for b in content[1:5]),
        "mac": content[5:11].hex().upper(),
        "device_type": header["device_type"],
    }


def parse_heartbeat_response(data: bytes) -> int | None:
    """0x61 心跳应答带设备自己的心跳间隔（秒）。"""
    header = parse_header(data)
    if header is None:
        return None
    content = header["content"]
    if len(content) >= 3 and content[0] == CMD_HEARTBEAT:
        return (content[1] << 8) | content[2]
    return None


def parse_filter_warning(data: bytes) -> int | None:
    """X50S 滤芯预警百分比：CONTENT[6]=0x84 且 CONTENT[11]=0x06 时取 CONTENT[13]。"""
    header = parse_header(data)
    if header is None:
        return None
    content = header["content"]
    if len(content) > 13 and content[6] == CMD_CONTROL_RESP and content[11] == SUB_FILTER_WARNING:
        return content[13]
    return None
