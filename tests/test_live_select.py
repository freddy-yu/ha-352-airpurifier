"""真机验证 select 实体（模式选择）与 fan 风速。

设备: 192.168.0.29 X50S。含关机状态下的模式选择场景。
"""

from __future__ import annotations

import asyncio
import enum
import importlib.util
import socket
import sys
import threading
import time
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352"
IP, PORT, MAC = "192.168.0.29", 11530, "F0FE6B9388FF"
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
    _attr_supported_color_modes = None
    _attr_color_mode = None

    def async_write_ha_state(self):
        pass


class FakeSelect(FakeEntity):
    pass


ha = types.ModuleType("homeassistant")
comp = types.ModuleType("homeassistant.components")
for name in ("fan", "light", "select"):
    sys.modules[f"homeassistant.components.{name}"] = types.ModuleType(
        f"homeassistant.components.{name}"
    )

fan_mod = sys.modules["homeassistant.components.fan"]
light_mod = sys.modules["homeassistant.components.light"]
select_mod = sys.modules["homeassistant.components.select"]
fan_mod.FanEntity = FakeEntity
fan_mod.FanEntityFeature = _Feature
light_mod.LightEntity = FakeEntity
select_mod.SelectEntity = FakeSelect


class ColorMode:
    ONOFF = "onoff"


light_mod.ColorMode = ColorMode
sys.modules["homeassistant"] = ha
sys.modules["homeassistant.components"] = comp

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
fanmod = _load("fan")
selectmod = _load("select")

seen = [0]


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", PORT))

    hub = hubmod.Air352Hub(None, IP, MAC, "x50s")
    stop = threading.Event()

    def rx():
        sock.settimeout(0.2)
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            if addr[0] in ("192.168.0.40", "127.0.0.1"):
                continue
            seen[0] += 1
            hub.parse_data(data, addr)

    threading.Thread(target=rx, daemon=True).start()

    fan = fanmod.Air352FanEntity(hub)
    sel = selectmod.Air352ModeSelect(hub)
    spd = selectmod.Air352SpeedSelect(hub)

    async def confirm(pred=None, timeout=8.0):
        before = seen[0]
        await hub.async_query()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if seen[0] > before and (pred is None or pred(hub.status)):
                await asyncio.sleep(0.4)
                return dict(hub.status)
            await asyncio.sleep(0.1)
        return dict(hub.status)

    async def run():
        await hub.async_discover()
        await asyncio.sleep(2.5)
        check("设备在线", hub.available, True)

        st = await confirm()
        orig_power = st["power"]
        print(f"   初始: power={st['power']} mode={st['mode']} speed={st['speed']}")

        print("\n=== 1. select 显示当前模式 ===")
        print(f"   current_option={sel.current_option}")
        check("选项完整", list(sel._attr_options), ["auto", "sleep", "turbo", "manual"])

        print("\n=== 2. 关机状态下用 select 选「睡眠」===")
        if hub.status["power"]:
            await hub.async_control("off")
            await confirm(lambda s: not s["power"], 6)
        check("已关机", hub.status["power"], False)

        await sel.async_select_option("sleep")
        await confirm(lambda s: s["mode"] == "sleep" and s["power"], 10)
        print(f"   power={hub.status['power']} mode={hub.status['mode']}")
        check("已开机", hub.status["power"], True)
        check("模式=sleep", hub.status["mode"], "sleep")
        check("select 已同步", sel.current_option, "sleep")

        print("\n=== 3. select 选「自动」===")
        await sel.async_select_option("auto")
        await confirm(lambda s: s["mode"] == "auto", 8)
        check("模式=auto", hub.status["mode"], "auto")

        print("\n=== 4. select 选「极速」===")
        await sel.async_select_option("turbo")
        await confirm(lambda s: s["mode"] == "turbo", 8)
        check("模式=turbo", hub.status["mode"], "turbo")

        print("\n=== 5. select 选「手动」+ fan 调风速 ===")
        await sel.async_select_option("manual")
        await confirm(lambda s: s["mode"] == "manual", 8)
        check("模式=manual", hub.status["mode"], "manual")

        await fan.async_set_percentage(80)
        await confirm(lambda s: s["speed"] == 4, 8)
        print(f"   speed={hub.status['speed']}")
        check("风速=4 (80%)", hub.status["speed"], 4)

        print("\n=== 6. fan 的 preset_mode 与 select 一致 ===")
        print(f"   fan.preset_mode={fan.preset_mode} select={sel.current_option}")
        check("fan 模式与 select 一致", fan.preset_mode, sel.current_option)

        print("\n=== 7. 风速档位 select 逐档设置 ===")
        print(f"   选项: {spd._attr_options}")
        for gear in (1, 2, 3, 4, 5):
            await spd.async_select_option(str(gear))
            await confirm(lambda s, g=gear: s["speed"] == g, 8)
            print(
                f"   选 {gear} 档 -> 上报 speed={hub.status['speed']} "
                f"select={spd.current_option} sensor={hub.status['speed']}"
            )
            check(f"{gear} 档生效", hub.status["speed"], gear)
            check(f"{gear} 档 select 同步", spd.current_option, str(gear))

        print("\n=== 8. 档位 select 与 fan.percentage 一致 ===")
        await spd.async_select_option("3")
        await confirm(lambda s: s["speed"] == 3, 8)
        print(f"   speed=3 -> fan.percentage={fan.percentage}")
        check("fan.percentage 对应 60%", fan.percentage, 60)

        print("\n=== 9. 自动模式下档位由设备决定 ===")
        await sel.async_select_option("auto")
        await confirm(lambda s: s["mode"] == "auto", 8)
        await asyncio.sleep(2)
        st = await confirm()
        print(f"   自动模式: speed={st['speed']} select={spd.current_option}")
        check("自动模式有合法档位值", st["speed"] in range(1, 7), True)

        print("\n=== 恢复 ===")
        await hub.async_control("auto")
        await asyncio.sleep(1.5)
        if not orig_power:
            await hub.async_control("off")
            await confirm(lambda s: not s["power"], 6)
            print("   恢复为关机")
        else:
            print("   保持开机")

    try:
        asyncio.run(run())
    finally:
        stop.set()
        sock.close()

    print()
    if FAILS:
        print(f"=== {len(FAILS)} 项失败 ===")
        for f in FAILS:
            print(" ", f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
