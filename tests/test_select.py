"""验证 select 实体（模式选择）以及 hub 的 set_mode/set_speed。"""

from __future__ import annotations

import asyncio
import enum
import importlib.util
import sys
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352"
FAILS = []


def check(label, actual, expected):
    if actual != expected:
        FAILS.append(f"{label}: 实际 {actual!r} 期望 {expected!r}")
        print(f"FAIL {label}")
    else:
        print(f"ok   {label}")


class _Feature(enum.IntFlag):
    SET_SPEED = 1
    PRESET_MODE = 8
    TURN_OFF = 16
    TURN_ON = 32


class FakeEntity:
    _attr_has_entity_name = False
    _attr_name = None
    _attr_unique_id = None
    _attr_icon = None
    _attr_translation_key = None
    _attr_options = None
    _attr_supported_features = 0
    _attr_preset_modes = None

    def async_write_ha_state(self):
        pass


class FakeSelect(FakeEntity):
    _attr_current_option = None


ha = types.ModuleType("homeassistant")
comp = types.ModuleType("homeassistant.components")
fan_mod = types.ModuleType("homeassistant.components.fan")
light_mod = types.ModuleType("homeassistant.components.light")
select_mod = types.ModuleType("homeassistant.components.select")

fan_mod.FanEntity = FakeEntity
fan_mod.FanEntityFeature = _Feature
light_mod.LightEntity = FakeEntity
select_mod.SelectEntity = FakeSelect


class ColorMode:
    ONOFF = "onoff"


light_mod.ColorMode = ColorMode
sys.modules.update({
    "homeassistant": ha,
    "homeassistant.components": comp,
    "homeassistant.components.fan": fan_mod,
    "homeassistant.components.light": light_mod,
    "homeassistant.components.select": select_mod,
})

pkg = types.ModuleType("air352")
pkg.__path__ = [str(COMP_DIR)]
sys.modules["air352"] = pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"air352.{name}", COMP_DIR / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"air352.{name}"] = m
    spec.loader.exec_module(m)
    return m


const = _load("const")
protocol = _load("protocol")
hubmod = _load("hub")
selectmod = _load("select")


class RecordingHub:
    def __init__(self, power=False, mode="auto"):
        self.mac = "F0FE6B9388FF"
        self.model = "x50s"
        self.info = const.model_info("x50s")
        self.speed_count = 5
        self.display_name = "352 X50S"
        self.available = True
        self.calls = []
        self.status = {"power": power, "speed": 1, "mode": mode, "light": True}

    async def async_set_mode(self, mode):
        if mode not in const.PRESET_MODES:
            return False
        if not self.status.get("power"):
            self.calls.append("on")
            self.status["power"] = True
        self.calls.append(mode)
        self.status["mode"] = mode
        return True

    async def async_set_speed(self, speed):
        if not self.status.get("power"):
            self.calls.append("on")
            self.status["power"] = True
        speed = max(1, min(self.speed_count, int(speed)))
        self.calls.append(f"speed_{speed}")
        self.status["speed"] = speed
        return True

    def register_callback(self, cb):
        pass

    def remove_callback(self, cb):
        pass


async def main():
    print("=== Select: 选项与当前值 ===")
    hub = RecordingHub(power=True, mode="auto")
    sel = selectmod.Air352ModeSelect(hub)
    check("选项列表", list(sel._attr_options), ["auto", "sleep", "turbo", "manual"])
    check("当前值", sel.current_option, "auto")
    check("翻译键", sel._attr_translation_key, "mode")

    print("\n=== Select: 选择睡眠（已开机）===")
    await sel.async_select_option("sleep")
    print(f"   命令: {hub.calls}")
    check("只发模式命令", hub.calls, ["sleep"])
    check("当前值已更新", sel.current_option, "sleep")

    print("\n=== Select: 关机状态选择手动 ===")
    hub2 = RecordingHub(power=False, mode="auto")
    sel2 = selectmod.Air352ModeSelect(hub2)
    await sel2.async_select_option("manual")
    print(f"   命令: {hub2.calls}")
    check("先开机再设模式", hub2.calls, ["on", "manual"])
    check("状态已更新", sel2.current_option, "manual")

    print("\n=== Select: 无效选项被忽略 ===")
    hub3 = RecordingHub(power=True)
    sel3 = selectmod.Air352ModeSelect(hub3)
    await sel3.async_select_option("bogus")
    check("无效选项不发命令", hub3.calls, [])

    print("\n=== Select: 未知模式返回 None ===")
    hub4 = RecordingHub(power=False, mode=None)
    hub4.status["mode"] = "mode4"
    sel4 = selectmod.Air352ModeSelect(hub4)
    check("未知模式不显示", sel4.current_option, None)

    print("\n=== 风速档位 Select: 选项与当前值 ===")
    hub5 = RecordingHub(power=True)
    hub5.status["speed"] = 3
    spd = selectmod.Air352SpeedSelect(hub5)
    check("选项为 1-5", spd._attr_options, ["1", "2", "3", "4", "5"])
    check("当前档位", spd.current_option, "3")
    check("翻译键", spd._attr_translation_key, "speed")

    print("\n=== 风速档位 Select: 选 4 档 ===")
    await spd.async_select_option("4")
    print(f"   命令: {hub5.calls}")
    check("发了 speed_4", hub5.calls, ["speed_4"])
    check("当前值已更新", spd.current_option, "4")

    print("\n=== 风速档位 Select: 关机状态选 2 档 ===")
    hub6 = RecordingHub(power=False)
    spd2 = selectmod.Air352SpeedSelect(hub6)
    await spd2.async_select_option("2")
    print(f"   命令: {hub6.calls}")
    check("先开机再设档", hub6.calls, ["on", "speed_2"])

    print("\n=== 风速档位 Select: 超范围选项被拒绝 ===")
    hub7 = RecordingHub(power=True)
    spd3 = selectmod.Air352SpeedSelect(hub7)
    await spd3.async_select_option("9")
    check("超范围不发命令", hub7.calls, [])
    await spd3.async_select_option("abc")
    check("非数字不发命令", hub7.calls, [])

    print("\n=== 风速档位 Select: 极速模式(6档)返回 None ===")
    hub8 = RecordingHub(power=True)
    hub8.status["speed"] = 6
    spd4 = selectmod.Air352SpeedSelect(hub8)
    check("6 档不在选项内 -> None", spd4.current_option, None)

    print("\n=== 风速档位 Select: X83 六档机型 ===")
    hub9 = RecordingHub(power=True)
    hub9.speed_count = 6
    spd5 = selectmod.Air352SpeedSelect(hub9)
    check("X83 选项 1-6", spd5._attr_options, ["1", "2", "3", "4", "5", "6"])

    print("\n=== Hub: async_set_mode 真实实现 ===")
    class FakeHub(hubmod.Air352Hub):
        def __init__(self):
            super().__init__(None, "192.168.1.2", "F0FE6B9388FF", "x50s", auth=0x1D05)
            self.sent = []
            self.status["power"] = False

        async def _async_send(self, packet, broadcast=False):
            self.sent.append(packet)
            return True

    fh = FakeHub()
    ok = await fh.async_set_mode("turbo")
    check("set_mode 返回 True", ok, True)
    check("发了 2 帧（on + mode）", len(fh.sent), 2)
    check("status.mode 已更新", fh.status["mode"], "turbo")
    check("status.power 已更新", fh.status["power"], True)

    print("\n=== Hub: 已开机时只发 1 帧 ===")
    fh2 = FakeHub()
    fh2.status["power"] = True
    await fh2.async_set_mode("sleep")
    check("只发 1 帧", len(fh2.sent), 1)

    print("\n=== Hub: 无效模式被拒绝 ===")
    fh3 = FakeHub()
    fh3.status["power"] = True
    ok = await fh3.async_set_mode("nope")
    check("返回 False", ok, False)
    check("没有发帧", len(fh3.sent), 0)

    print("\n=== Hub: async_set_speed 夹取范围 ===")
    fh4 = FakeHub()
    fh4.status["power"] = True
    await fh4.async_set_speed(99)
    check("超范围夹到 5", fh4.status["speed"], 5)
    await fh4.async_set_speed(0)
    check("下界夹到 1", fh4.status["speed"], 1)

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
