"""诊断「累计净化空气量」是否真的会变。

持续采样 body[22..23]（total_purification）和 body[25..26]
（cumulative_purification），观察设备开机运行时是否增长。
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import threading
import time
import types
from pathlib import Path

COMP_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "air_352_x50s"
)
IP, PORT = "192.168.0.29", 11530
MAC, COMPANY, DEVTYPE, AUTH = "F0FE6B9388FF", 0xF2, 0x03, 0x1D05

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

state = {}
seen = [0]


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
        seen[0] += 1
        s = protocol.parse_state(data)
        if s:
            body = data[24:-2]
            s["_b21"] = body[21] if len(body) > 21 else None
            s["_b22_23"] = (body[22] << 8) | body[23] if len(body) > 23 else None
            s["_b24"] = body[24] if len(body) > 24 else None
            s["_b25_26"] = (body[25] << 8) | body[26] if len(body) > 26 else None
            state.update(s)


seq = [900]


def send(sock, p5, p6):
    seq[0] += 1
    pkt = protocol.build_f072_command(MAC, COMPANY, DEVTYPE, AUTH, seq[0], p5, p6)
    sock.sendto(pkt, (IP, PORT))


def query(sock, timeout=3.0):
    before = seen[0]
    send(sock, 0x11, 0x11)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if seen[0] > before:
            time.sleep(0.4)
            return dict(state)
        time.sleep(0.05)
    return None


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", PORT))
    stop = threading.Event()
    threading.Thread(target=rx, args=(sock, stop), daemon=True).start()
    time.sleep(0.4)

    st = query(sock)
    if st is None:
        print("设备无应答")
        return 1
    print(f"初始: power={st['power']} mode={st['mode']} speed={st['speed']}")

    print("\n=== 确保开机并高速运行（最大化净化量增长速度）===")
    if not st["power"]:
        send(sock, 0x5E, 0x00)
        time.sleep(3)
    # 手动 5 档
    send(sock, 0x51, 0x04)
    time.sleep(1.5)
    send(sock, 0x52, 0x05)
    time.sleep(2)
    st = query(sock)
    print(f"   现在: power={st['power']} mode={st['mode']} speed={st['speed']}")

    print("\n=== 采样 6 次 x 25 秒，观察字段变化 ===")
    print(
        f"{'时刻':>6} {'pm25':>5} {'speed':>5} "
        f"{'scale21':>8} {'val22_23':>9} {'scale24':>8} {'val25_26':>9} "
        f"{'total_pur':>10} {'cumul':>10}"
    )
    samples = []
    for i in range(6):
        st = query(sock)
        if st:
            row = (
                i * 25,
                st["pm25"],
                st["speed"],
                st["_b21"],
                st["_b22_23"],
                st["_b24"],
                st["_b25_26"],
                st["total_purification"],
                st["cumulative_purification"],
            )
            samples.append(row)
            print(
                f"{row[0]:>6}s {row[1]:>5} {row[2]:>5} "
                f"{row[3]:>8} {row[4]:>9} {row[5]:>8} {row[6]:>9} "
                f"{row[7]:>10} {row[8]:>10}"
            )
        if i < 5:
            time.sleep(22)

    print("\n=== 分析 ===")
    if len(samples) >= 2:
        cumuls = {s[8] for s in samples}
        vals = {s[6] for s in samples}
        totals = {s[7] for s in samples}
        print(f"   cumulative_purification 出现过的值: {sorted(cumuls)}")
        print(f"   body[25..26] 原始值: {sorted(vals)}")
        print(f"   total_purification 出现过的值: {sorted(totals)}")
        print(f"   -> cumulative {'在变' if len(cumuls) > 1 else '不变'}")
        print(f"   -> body[25..26] {'在变' if len(vals) > 1 else '不变'}")

    print("\n=== 恢复 ===")
    send(sock, 0x51, 0x01)
    time.sleep(1.5)
    send(sock, 0x5E, 0x11)
    time.sleep(2)
    st = query(sock)
    if st:
        print(f"   已关机: power={st['power']}")

    stop.set()
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
