"""诊断：风速档位上报是否随命令变化，以及 sensor 实体能否读到。

重点核对状态帧原始字节 body[4]，确认解析偏移没问题。
设备: 192.168.0.29 X50S
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import threading
import time
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352"
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
raw_info = {"body4": None, "raw": None}
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
            state.update(s)
            # 记录原始 body[4]
            body = data[24:-2]
            if len(body) > 4:
                raw_info["body4"] = body[4]
                raw_info["raw"] = data.hex(" ").upper()


seq = [800]


def send(sock, p5, p6):
    seq[0] += 1
    pkt = protocol.build_f072_command(MAC, COMPANY, DEVTYPE, AUTH, seq[0], p5, p6)
    sock.sendto(pkt, (IP, PORT))


def query(sock):
    before = seen[0]
    send(sock, 0x11, 0x11)
    deadline = time.time() + 3.0
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

    if not st["power"]:
        print("\n开机...")
        send(sock, 0x5E, 0x00)
        time.sleep(2.0)
        query(sock)

    print("\n=== 切到手动模式 ===")
    send(sock, 0x51, 0x04)
    time.sleep(2.0)
    st = query(sock)
    print(f"   mode={st['mode']} speed={st['speed']}")

    print("\n=== 手动模式逐档设置，每次查询确认 ===")
    rows = []
    for gear in (1, 2, 3, 4, 5):
        send(sock, 0x52, gear)
        time.sleep(2.0)
        st = query(sock)
        if st:
            rows.append((gear, st["speed"], raw_info["body4"], st["mode"]))
            print(
                f"   设 {gear} -> 上报 speed={st['speed']}  "
                f"原始body[4]=0x{raw_info['body4']:02X}  mode={st['mode']}"
            )
        else:
            print(f"   设 {gear} -> 无应答")

    print("\n=== 自动模式下的 speed ===")
    send(sock, 0x51, 0x01)
    time.sleep(3.0)
    for _ in range(3):
        st = query(sock)
        if st:
            print(f"   mode={st['mode']} speed={st['speed']} body[4]=0x{raw_info['body4']:02X}")
        time.sleep(1.5)

    print("\n=== 极速模式下的 speed ===")
    send(sock, 0x51, 0x03)
    time.sleep(3.0)
    st = query(sock)
    if st:
        print(f"   mode={st['mode']} speed={st['speed']} body[4]=0x{raw_info['body4']:02X}")

    print("\n=== 结论 ===")
    ok = all(r[0] == r[1] for r in rows)
    print(f"   手动档位逐档对应: {'正确' if ok else '有偏差'}")
    for gear, got, b4, mode in rows:
        print(f"     设{gear} -> {got} (body[4]=0x{b4:02X})")

    print("\n=== 恢复 ===")
    send(sock, 0x51, 0x01)
    time.sleep(1.5)
    send(sock, 0x5E, 0x11)
    time.sleep(2.0)
    st = query(sock)
    if st:
        print(f"   已关机: power={st['power']}")

    stop.set()
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
