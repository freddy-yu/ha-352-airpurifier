"""严谨探测：每条命令后主动查询确认，查询响应作为权威判据。

避免被动收包丢包导致的误判。
"""

from __future__ import annotations

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
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"air352.{name}"] = m
    spec.loader.exec_module(m)
    return m


protocol = _load("protocol")
IP, PORT = "192.168.0.29", 11530
MAC, COMPANY, DEVTYPE, AUTH = "F0FE6B9388FF", 0xF2, 0x03, 0x1D05

state = {}
frames_seen = [0]


def rx(sock, stop):
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
        frames_seen[0] += 1
        s = protocol.parse_state(data)
        if s:
            state.update(s)


seq = [700]


def send(sock, p5, p6):
    seq[0] += 1
    pkt = protocol.build_f072_command(MAC, COMPANY, DEVTYPE, AUTH, seq[0], p5, p6)
    sock.sendto(pkt, (IP, PORT))


def query(sock):
    """发查询并等待应答，返回当前状态。"""
    before = frames_seen[0]
    send(sock, 0x11, 0x11)
    deadline = time.time() + 2.5
    while time.time() < deadline:
        if frames_seen[0] > before:
            time.sleep(0.3)  # 多收几帧，拿最新
            return dict(state)
        time.sleep(0.05)
    return None


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", PORT))
    except OSError as e:
        print(f"绑定 {PORT} 失败: {e}")
        return 1

    stop = threading.Event()
    threading.Thread(target=rx, args=(sock, stop), daemon=True).start()
    time.sleep(0.5)

    def step(label, p5, p6, settle=2.0):
        send(sock, p5, p6)
        time.sleep(settle)
        st = query(sock)
        if st is None:
            print(f"  {label:<26} -> 无应答")
            return None
        print(
            f"  {label:<26} -> power={st['power']!s:<5} light={st['light']!s:<5} "
            f"speed={st['speed']} mode={st['mode']}"
        )
        return st

    print("=== 初始 ===")
    st = query(sock)
    if st is None:
        print("设备无应答，检查 IP/网络")
        return 1
    print(f"  power={st['power']} light={st['light']} speed={st['speed']} mode={st['mode']}")

    print("\n=== 1. 确保开机 ===")
    if not st["power"]:
        st = step("开机", 0x5E, 0x00, 6)
    else:
        print("  已是开机")

    print("\n=== 2. 灯光：开 -> 关 -> 开 ===")
    step("开灯 0x56/0x00", 0x56, 0x00, 2.5)
    step("关灯 0x56/0x11", 0x56, 0x11, 2.5)
    step("再开灯 0x56/0x00", 0x56, 0x00, 2.5)
    step("再关灯 0x56/0x11", 0x56, 0x11, 2.5)

    print("\n=== 3. 模式切换（开机状态）===")
    step("自动 0x51/0x01", 0x51, 0x01, 3)
    step("睡眠 0x51/0x02", 0x51, 0x02, 3)
    step("极速 0x51/0x03", 0x51, 0x03, 3)
    step("手动 0x51/0x04", 0x51, 0x04, 3)

    print("\n=== 4. 风速（开机状态）===")
    step("风速1 0x52/0x01", 0x52, 0x01, 2.5)
    step("风速3 0x52/0x03", 0x52, 0x03, 2.5)
    step("风速5 0x52/0x05", 0x52, 0x05, 2.5)

    print("\n=== 5. 关机后连发 on+speed（模拟原 bug）===")
    step("关机", 0x5E, 0x11, 4)
    send(sock, 0x5E, 0x00)
    send(sock, 0x52, 0x04)   # 背靠背，无间隔
    time.sleep(4)
    st = query(sock)
    print(f"  背靠背 on+speed_4 -> power={st['power']} speed={st['speed']}")
    print(f"  {'OK 生效' if st['speed']==4 else 'FAIL 被覆盖'}")

    print("\n=== 6. 关机后 on -> 等 1.2s -> speed（修复方案）===")
    step("关机", 0x5E, 0x11, 4)
    send(sock, 0x5E, 0x00)
    time.sleep(1.2)
    send(sock, 0x52, 0x04)
    time.sleep(4)
    st = query(sock)
    print(f"  间隔1.2s on+speed_4 -> power={st['power']} speed={st['speed']}")
    print(f"  {'OK 生效' if st['speed']==4 else 'FAIL'}")

    print("\n=== 恢复 ===")
    step("自动", 0x51, 0x01, 2)
    step("关机", 0x5E, 0x11, 3)

    stop.set()
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
