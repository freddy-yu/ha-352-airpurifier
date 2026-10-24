"""模拟 HA 实体层，验证 fan/light 实际发出的命令序列。

之前只测了 hub 层，从未测过 fan.py / light.py，用户反馈的问题正是这一层。
不依赖真实 Home Assistant：用最小 stub 替换 HA 基类。
"""

from __future__ import annotations

import asyncio
import enum
import importlib.util
import sys
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352_x50s"

FAILS = []


def check(label, actual, expected):
    if actual != expected:
        FAILS.append(f"{label}: 实际 {actual!r} 期望 {expected!r}")
        print(f"FAIL {label}")
    else:
        print(f"ok   {label}")


# ---------------------------------------------------------------- HA stubs
class _Feature(enum.IntFlag):
    TURN_ON = 1
    TURN_OFF = 2
    SET_SPEED = 4
    PRESET_MODE = 8
    OSCILLATING = 16


class FakeEntity:
    """最小实体基类，记录状态写入次数。"""

    _attr_has_entity_name = False
    _attr_name = None
    _attr_unique_id = None
    _attr_icon = None
    _attr_supported_features = 0
    _attr_speed_count = None
    _attr_preset_modes = None
    _attr_supported_color_modes = None
    _attr_color_mode = None
    _attr_device_class = None
    _attr_state_class = None
    _attr_native_unit_of_measurement = None
    _attr_entity_category = None

    # 子类自定义 __init__ 不会调 super()，所以计数器放类属性
    writes = 0

    def async_write_ha_state(self):
        type(self).writes += 1

    @property
    def available(self):
        return True


class FakeFan(FakeEntity):
    pass


class FakeLight(FakeEntity):
    pass


def _install_stubs():
    ha = types.ModuleType("homeassistant")
    comp = types.ModuleType("homeassistant.components")
    fan_mod = types.ModuleType("homeassistant.components.fan")
    light_mod = types.ModuleType("homeassistant.components.light")

    fan_mod.FanEntity = FakeFan
    fan_mod.FanEntityFeature = _Feature
    light_mod.LightEntity = FakeLight

    class ColorMode:
        ONOFF = "onoff"

    light_mod.ColorMode = ColorMode

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.components"] = comp
    sys.modules["homeassistant.components.fan"] = fan_mod
    sys.modules["homeassistant.components.light"] = light_mod

    pkg = types.ModuleType("air352")
    pkg.__path__ = [str(COMP_DIR)]
    sys.modules["air352"] = pkg


_install_stubs()


def _load(name):
    spec = importlib.util.spec_from_file_location(f"air352.{name}", COMP_DIR / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"air352.{name}"] = m
    spec.loader.exec_module(m)
    return m


const = _load("const")
protocol = _load("protocol")
hubmod = _load("hub")
fanmod = _load("fan")
lightmod = _load("light")


class RecordingHub:
    """记录所有 async_control 调用的假 hub。"""

    def __init__(self, model="x50s"):
        self.mac = "F0FE6B9388FF"
        self.model = model
        self.info = const.model_info(model)
        self.speed_count = self.info["speed_count"]
        self.display_name = self.info["name"]
        self.available = True
        self.calls = []
        self.status = {
            "power": False,
            "speed": 1,
            "mode": "auto",
            "light": True,
            "pm25": 10,
        }

    async def async_control(self, action):
        self.calls.append(action)
        return True

    async def _async_ensure_power_on(self):
        if self.status.get("power"):
            return True
        self.calls.append("on")
        self.status["power"] = True
        return True

    async def async_set_mode(self, mode):
        if mode not in const.PRESET_MODES:
            return False
        await self._async_ensure_power_on()
        self.calls.append(mode)
        self.status["mode"] = mode
        return True

    async def async_set_speed(self, speed):
        await self._async_ensure_power_on()
        self.calls.append(f"speed_{speed}")
        self.status["speed"] = speed
        return True

    def register_callback(self, cb):
        pass

    def remove_callback(self, cb):
        pass


# ------------------------------------------------------------------ 测试
async def main():
    print("=== Fan: 关机状态点「自动」模式 ===")
    hub = RecordingHub()
    fan = fanmod.Air352FanEntity(hub)
    await fan.async_set_preset_mode("auto")
    print(f"   发出的命令: {hub.calls}")
    check("模式命令已发出", "auto" in hub.calls, True)
    check(
        "关机时应先开机再切模式",
        hub.calls,
        ["on", "auto"],
    )

    print("\n=== Fan: 已开机点「睡眠」模式 ===")
    hub2 = RecordingHub()
    hub2.status["power"] = True
    fan2 = fanmod.Air352FanEntity(hub2)
    await fan2.async_set_preset_mode("sleep")
    print(f"   发出的命令: {hub2.calls}")
    check("已开机只发模式命令", hub2.calls, ["sleep"])

    print("\n=== Fan: 关机状态调风速 ===")
    hub3 = RecordingHub()
    fan3 = fanmod.Air352FanEntity(hub3)
    await fan3.async_set_percentage(40)
    print(f"   发出的命令: {hub3.calls}")
    check("风速命令", hub3.calls, ["on", "speed_2"])

    print("\n=== Fan: preset_mode 属性 ===")
    hub4 = RecordingHub()
    hub4.status["mode"] = "manual"
    fan4 = fanmod.Air352FanEntity(hub4)
    check("manual 可被 HA 识别", fan4.preset_mode, "manual")
    hub4.status["mode"] = None
    check("未知模式返回 None", fan4.preset_mode, None)

    print("\n=== Light: 设备关机但灯亮着（实测真实状态）===")
    hub5 = RecordingHub()
    hub5.status["power"] = False
    hub5.status["light"] = True
    light = lightmod.Air352LightEntity(hub5)
    print(f"   power=False light=True -> is_on={light.is_on}")
    check("关机时灯亮应显示为开", light.is_on, True)

    print("\n=== Light: 开灯命令 ===")
    hub6 = RecordingHub()
    hub6.status["power"] = False
    hub6.status["light"] = False
    light2 = lightmod.Air352LightEntity(hub6)
    await light2.async_turn_on()
    print(f"   发出的命令: {hub6.calls}")
    check("开灯命令", hub6.calls, ["light_on"])

    print()
    if FAILS:
        print(f"=== {len(FAILS)} 项失败 ===")
        for f in FAILS:
            print(" ", f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
