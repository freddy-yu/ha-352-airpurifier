"""352 空气净化器集成的常量定义。"""

from .protocol import PROTOCOL_A5A0, PROTOCOL_F072

DOMAIN = "air_352_x50s"
NAME = "352 X50S Air Purifier"

UDP_PORT = 11530
TCP_PORT = 11591

# 厂商码
COMPANY_CODE_LRD = 0xF1
COMPANY_CODE_HF = 0xF2

# App 侧固定认证码，用于局域网搜索（设备尚不知情时）
APP_AUTH_CODE = 0xCB76

# 设备默认认证码，可在配置里覆盖；收到设备帧后会自动学习真实值
DEFAULT_DEVICE_AUTH = 0x0504

# 设备类型码（协议层）
DEVICE_TYPE_X83 = 0x02
DEVICE_TYPE_X50 = 0x03
DEVICE_TYPE_G30 = 0x04

HEARTBEAT_INTERVAL = 5
QUERY_INTERVAL = 60

# 设备开机后有一段初始化（风速会自己跳几下），
# 紧跟的命令可能被覆盖，需等待稳定。
POWER_ON_SETTLE = 0.8

# 每个模型的协议参数
#   protocol     : 内层帧格式
#   device_type  : 外层头 DEVICE_TYPE
#   speed_count  : 风速档数（UI 可选的档位）
#   features     : 该模型上报里可用字段
MODELS = {
    "x50s": {
        "name": "352 X50S 空气净化器",
        "protocol": PROTOCOL_F072,
        "device_type": DEVICE_TYPE_X50,
        "speed_count": 5,
        "fetch_state": True,
        # 实测无温湿度/CO2 传感器（上报恒为 0）
        "extra_sensors": [],
        # 实测不支持的命令（发了设备无反应）
        "unsupported": [
            "timer_off", "timer_1h", "timer_2h",
            "timer_3h", "timer_5h", "timer_8h",
        ],
    },
    "x50": {
        "name": "352 X50 空气净化器",
        # 老固件沿用 A5 A0 帧，避免破坏现有用户
        "protocol": PROTOCOL_A5A0,
        "device_type": DEVICE_TYPE_X50,
        "speed_count": 5,
        "fetch_state": True,
        "extra_sensors": [],
    },
    "x60": {
        "name": "352 X60 空气净化器",
        "protocol": PROTOCOL_F072,
        "device_type": DEVICE_TYPE_X50,
        "speed_count": 5,
        "fetch_state": True,
        "extra_sensors": ["temperature", "humidity", "co2"],
    },
    "x70": {
        "name": "352 X70 空气净化器",
        "protocol": PROTOCOL_F072,
        "device_type": DEVICE_TYPE_X50,
        "speed_count": 5,
        "fetch_state": True,
        "extra_sensors": ["temperature", "humidity", "co2"],
    },
    "x83": {
        "name": "352 X83 空气净化器",
        "protocol": PROTOCOL_A5A0,
        "device_type": DEVICE_TYPE_X83,
        "speed_count": 6,
        "fetch_state": True,
        "extra_sensors": [],
    },
    "x83c": {
        "name": "352 X83C 空气净化器",
        "protocol": PROTOCOL_A5A0,
        "device_type": DEVICE_TYPE_X83,
        "speed_count": 6,
        "fetch_state": True,
        "extra_sensors": [],
    },
    "g30": {
        "name": "352 G30 新风净化机",
        "protocol": PROTOCOL_F072,
        "device_type": DEVICE_TYPE_G30,
        "speed_count": 5,
        "fetch_state": True,
        "extra_sensors": ["temperature", "humidity", "co2"],
    },
}

MODEL_ALIASES = {"x50s": "x50s", "x50": "x50", "x83cplus": "x83"}

PRESET_MODES = ["auto", "sleep", "turbo", "manual"]

# F0 72 帧的 (P5, P6) 参数对
#   P6 取值约定：0x00 = 开，0x11 = 关（与 App 一致）
COMMANDS_F072 = {
    "query": (0x11, 0x11),
    "on": (0x5E, 0x00),
    "off": (0x5E, 0x11),
    "light_on": (0x56, 0x00),
    "light_off": (0x56, 0x11),
    "auto": (0x51, 0x01),
    "sleep": (0x51, 0x02),
    "turbo": (0x51, 0x03),
    # X50S 实测：0x04 才是手动，0x05 设备无响应
    "manual": (0x51, 0x04),
    "ptc_0": (0x53, 0x00),
    "ptc_1": (0x53, 0x01),
    "ptc_2": (0x53, 0x02),
    "child_lock_on": (0x55, 0x00),
    "child_lock_off": (0x55, 0x11),
    "timer_off": (0x54, 0x00),
    "timer_1h": (0x54, 0x01),
    "timer_2h": (0x54, 0x02),
    "timer_3h": (0x54, 0x03),
    "timer_5h": (0x54, 0x05),
    "timer_8h": (0x54, 0x08),
}
for _i in range(1, 7):
    COMMANDS_F072[f"speed_{_i}"] = (0x52, _i)

# 老 A5 A0 帧（X83/X83C）的 (P5, P6) 参数对
COMMANDS_A5A0 = {
    "query": (0x11, 0x11),
    "on": (0x5E, 0x00),
    "off": (0x5E, 0x11),
    "light_on": (0x56, 0x00),
    "light_off": (0x56, 0x11),
    "auto": (0x51, 0x01),
    "sleep": (0x51, 0x02),
    "turbo": (0x51, 0x03),
    "manual": (0x51, 0x04),
    "ptc_0": (0x53, 0x00),
    "ptc_1": (0x53, 0x01),
    "ptc_2": (0x53, 0x02),
    "child_lock_on": (0x55, 0x00),
    "child_lock_off": (0x55, 0x11),
    "timer_off": (0x54, 0x00),
    "timer_1h": (0x54, 0x01),
    "timer_2h": (0x54, 0x02),
    "timer_3h": (0x54, 0x03),
    "timer_5h": (0x54, 0x05),
    "timer_8h": (0x54, 0x08),
}
for _i in range(1, 7):
    COMMANDS_A5A0[f"speed_{_i}"] = (0x52, _i)

# 兼容旧代码引用
COMMANDS = COMMANDS_A5A0


def model_info(model: str) -> dict:
    key = (model or "x50s").lower()
    key = MODEL_ALIASES.get(key, key)
    return MODELS.get(key, MODELS["x50s"])


def commands_for(model: str) -> dict:
    info = model_info(model)
    if info["protocol"] == PROTOCOL_A5A0:
        return COMMANDS_A5A0
    return COMMANDS_F072
