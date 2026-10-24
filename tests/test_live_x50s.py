"""用真实 X50S 验证集成代码路径（hub.py）。

验证的是插件实际逻辑，不是探测脚本：
  * 认证码自动学习
  * 状态解析与锁定
  * 命令分发（含 A5 A0 / F0 72 选择）
  * 在线检测

运行后会恢复设备到初始电源状态。
"""

from __future__ import annotations

import asyncio
import importlib.util
import socket
import sys
import threading
import time
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352_x50s"
pkg = types.ModuleType("air352")
pkg.__path__ = [str(COMP_DIR)]
sys.modules["air352"] = pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"air352.{name}", COMP_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"air352.{name}"] = module
    spec.loader.exec_module(module)
    return module


const = _load("const")
protocol = _load("protocol")
hub_mod = _load("hub")

IP = "192.168.0.29"
PORT = 11530
MAC = "F0FE6B9388FF"

FAILS = []


def check(label, actual, expected):
    if actual != expected:
        FAILS.append(f"{label}: 实际 {actual!r} 期望 {expected!r}")
        print(f"FAIL {label}")
    else:
        print(f"ok   {label}")


class Collector:
    def __init__(self, hub):
        self.hub = hub
        self.hits = 0

    def __call__(self):
        self.hits += 1


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", PORT))

    hub = hub_mod.Air352Hub(None, IP, MAC, "x50s")
    collector = Collector(hub)
    hub.register_callback(collector)

    stop = threading.Event()

    def rx():
        sock.settimeout(0.3)
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            if addr[0] in ("192.168.0.40", "127.0.0.1"):
                continue
            hub.parse_data(data, addr)

    threading.Thread(target=rx, daemon=True).start()

    async def run():
        print("=== 1. 初始状态 ===")
        check("初始 company", hub.company, const.COMPANY_CODE_LRD)
        check("初始 auth", hub.auth, const.DEFAULT_DEVICE_AUTH)
        check("初始离线", hub.available, False)

        print("\n=== 2. 搜索（触发认证码学习）===")
        await hub.async_discover()
        await asyncio.sleep(3.0)
        check("搜索后在线", hub.available, True)
        check("学到真实 auth", hub.auth, 0x1D05)
        check("学到真实 company", hub.company, 0xF2)
        check("回调被触发", collector.hits > 0, True)

        print("\n=== 3. 查询状态 ===")
        await hub.async_query()
        await asyncio.sleep(2.5)
        state = dict(hub.status)
        print(f"   状态: {state}")
        check("状态已更新", state["power"] in (True, False), True)
        check("PM2.5 是整数", isinstance(state["pm25"], int), True)

        initial_power = state["power"]
        print(f"   设备当前电源: {'开' if initial_power else '关'}")

        print("\n=== 4. 控制：开机 ===")
        await hub.async_control("on")
        await asyncio.sleep(4.5)
        check("开机生效", hub.status["power"], True)

        print("\n=== 5. 控制：切手动模式（避免自动调速干扰）===")
        await hub.async_control("manual")
        await asyncio.sleep(3.0)
        check("模式 = manual", hub.status["mode"], "manual")

        print("\n=== 6. 控制：风速 2 档 ===")
        await hub.async_control("speed_2")
        await asyncio.sleep(3.0)
        check("风速 = 2", hub.status["speed"], 2)

        print("\n=== 7. 控制：自动模式 ===")
        await hub.async_control("auto")
        await asyncio.sleep(3.0)
        check("模式 = auto", hub.status["mode"], "auto")

        print("\n=== 8. 恢复初始状态 ===")
        if initial_power:
            await hub.async_control("on")
            print("   恢复为开机")
        else:
            await hub.async_control("off")
            print("   恢复为关机")
        await asyncio.sleep(4.0)
        check("已恢复", hub.status["power"], initial_power)

        print("\n=== 9. 离线检测 ===")
        hub.last_seen = time.monotonic() - 120
        hub.check_availability(timeout=60)
        check("超时后离线", hub.available, False)

    try:
        asyncio.run(run())
    finally:
        stop.set()
        sock.close()

    print()
    if FAILS:
        print(f"=== {len(FAILS)} 项失败 ===")
        for item in FAILS:
            print(item)
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
