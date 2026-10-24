"""验证灯光与童锁命令（只读语义，顺序恢复）。"""

from __future__ import annotations

import asyncio
import importlib.util
import socket
import sys
import threading
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352_x83"
pkg = types.ModuleType("air352")
pkg.__path__ = [str(COMP_DIR)]
sys.modules["air352"] = pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"air352.{name}", COMP_DIR / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"air352.{name}"] = m
    spec.loader.exec_module(m)
    return m


protocol = _load("protocol")
hub_mod = _load("hub")

IP, PORT, MAC = "192.168.0.29", 11530, "F0FE6B9388FF"
FAILS = []


def check(label, actual, expected):
    if actual != expected:
        FAILS.append(f"{label}: 实际 {actual!r} 期望 {expected!r}")
        print(f"FAIL {label}")
    else:
        print(f"ok   {label}")


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", PORT))
    hub = hub_mod.Air352Hub(None, IP, MAC, "x50s")
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
        await hub.async_query()
        await asyncio.sleep(2.5)
        check("上线", hub.available, True)

        orig_power = hub.status["power"]
        orig_light = hub.status["light"]
        print(f"   初始: power={orig_power} light={orig_light} lock={hub.status['child_lock']}")

        # 确保开机，灯光才有意义（开机后需等设备稳定）
        if not orig_power:
            await hub.async_control("on")
            await asyncio.sleep(6)

        print("\n=== 灯光 ===")
        await hub.async_control("light_off")
        await asyncio.sleep(3.5)
        check("关灯生效", hub.status["light"], False)

        await hub.async_control("light_on")
        await asyncio.sleep(3.5)
        check("开灯生效", hub.status["light"], True)

        print("\n=== 童锁 ===")
        await hub.async_control("child_lock_on")
        await asyncio.sleep(3.5)
        check("上锁生效", hub.status["child_lock"], True)

        await hub.async_control("child_lock_off")
        await asyncio.sleep(3.5)
        check("解锁生效", hub.status["child_lock"], False)

        # 定时：X50S 对 0x54 无响应，已知限制，不做断言
        print("\n=== 定时（X50S 不支持，仅记录）===")
        await hub.async_control("timer_2h")
        await asyncio.sleep(3)
        print(f"   发 0x54/0x02 后 timer={hub.status['timer']}（预期 0，设备不支持）")
        await hub.async_control("timer_off")
        await asyncio.sleep(2)

        print("\n=== 恢复 ===")
        if not orig_light:
            await hub.async_control("light_off")
        if not orig_power:
            await hub.async_control("off")
            print("   恢复为关机")
        await asyncio.sleep(3)

    try:
        asyncio.run(run())
    finally:
        stop.set()
        sock.close()

    print()
    if FAILS:
        print(f"=== {len(FAILS)} 项失败 ===")
        for f in FAILS:
            print(f)
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
