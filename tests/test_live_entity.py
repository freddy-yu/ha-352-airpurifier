"""真机验证实体层：走 fan.py / light.py 真实代码路径。

用「每条命令后主动查询」作为判据，避免被动收包丢包导致的误判。
设备: 192.168.0.29  X50S。运行后恢复设备初始电源状态。
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

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352_x50s"
IP, PORT, MAC = "192.168.0.29", 11530, "F0FE6B9388FF"

FAILS = []


def check(label, actual, expected):
    if actual != expected:
        FAILS.append(f"{label}: 实际 {actual!r} 期望 {expected!r}")
        print(f"FAIL {label}")
    else:
        print(f"ok   {label}")


class _Feature(enum.IntFlag):
    TURN_ON = 1
    TURN_OFF = 2
    SET_SPEED = 4
    PRESET_MODE = 8


class FakeEntity:
    _attr_has_entity_name = False
    _attr_name = None
    _attr_unique_id = None
    _attr_icon = None
    _attr_supported_features = 0
    _attr_speed_count = None
    _attr_preset_modes = None
    _attr_supported_color_modes = None
    _attr_color_mode = None
    writes = 0

    def async_write_ha_state(self):
        type(self).writes += 1


ha = types.ModuleType("homeassistant")
comp = types.ModuleType("homeassistant.components")
fan_mod = types.ModuleType("homeassistant.components.fan")
light_mod = types.ModuleType("homeassistant.components.light")
fan_mod.FanEntity = FakeEntity
fan_mod.FanEntityFeature = _Feature
light_mod.LightEntity = FakeEntity


class ColorMode:
    ONOFF = "onoff"


light_mod.ColorMode = ColorMode
sys.modules.update({
    "homeassistant": ha,
    "homeassistant.components": comp,
    "homeassistant.components.fan": fan_mod,
    "homeassistant.components.light": light_mod,
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
fanmod = _load("fan")
lightmod = _load("light")

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
    light = lightmod.Air352LightEntity(hub)

    async def confirm(predicate=None, timeout=4.0):
        """发查询，等到状态满足 predicate 或超时。返回最终状态快照。"""
        before = seen[0]
        await hub.async_query()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if seen[0] > before and (predicate is None or predicate(hub.status)):
                await asyncio.sleep(0.4)
                return dict(hub.status)
            await asyncio.sleep(0.1)
        return dict(hub.status)

    async def run():
        await hub.async_discover()
        await asyncio.sleep(2.5)
        check("设备在线", hub.available, True)
        check("认证码已学习", hub.auth, 0x1D05)

        st = await confirm()
        orig_power = st["power"]
        print(f"   初始: power={st['power']} light={st['light']} mode={st['mode']}")

        # 统一从关机开始，复现用户场景
        if st["power"]:
            await hub.async_control("off")
            await confirm(lambda s: not s["power"], 6)
        check("起始为关机", hub.status["power"], False)

        print("\n=== 1. 关机状态点「睡眠」===")
        await fan.async_set_preset_mode("sleep")
        await confirm(lambda s: s["mode"] == "sleep", 8)
        print(f"   power={hub.status['power']} mode={hub.status['mode']}")
        check("模式切到 sleep", hub.status["mode"], "sleep")
        check("设备已开机", hub.status["power"], True)

        print("\n=== 2. 点「手动」===")
        await fan.async_set_preset_mode("manual")
        await confirm(lambda s: s["mode"] == "manual", 6)
        check("模式切到 manual", hub.status["mode"], "manual")

        print("\n=== 3. 点「自动」===")
        await fan.async_set_preset_mode("auto")
        await confirm(lambda s: s["mode"] == "auto", 6)
        check("模式切到 auto", hub.status["mode"], "auto")

        print("\n=== 4. 灯光（开机状态，双向）===")
        await light.async_turn_off()
        await confirm(lambda s: s["light"] is False, 6)
        check("关灯生效", hub.status["light"], False)
        check("实体显示关", light.is_on, False)

        await light.async_turn_on()
        await confirm(lambda s: s["light"] is True, 6)
        check("开灯生效", hub.status["light"], True)
        check("实体显示开", light.is_on, True)
        check("开机时灯光可用", light.available, True)

        print("\n=== 5. 关机后调风速（原先会被初始化覆盖）===")
        await hub.async_control("off")
        await confirm(lambda s: not s["power"], 6)
        check("关机时灯光标记不可用", light.available, False)

        await fan.async_set_percentage(60)
        await confirm(lambda s: s["speed"] == 3 and s["power"], 10)
        print(f"   power={hub.status['power']} speed={hub.status['speed']}")
        check("风速设为 3", hub.status["speed"], 3)
        check("设备已开机", hub.status["power"], True)

        print("\n=== 恢复初始 ===")
        await hub.async_control("auto")
        await asyncio.sleep(1.5)
        if orig_power:
            print("   恢复为开机(auto)")
        else:
            await hub.async_control("off")
            await confirm(lambda s: not s["power"], 6)
            print("   恢复为关机")

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
