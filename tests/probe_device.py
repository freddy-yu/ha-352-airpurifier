"""X50S 局域网诊断：先被动监听，再主动搜索。

用法:
    python tests/probe_device.py 192.168.0.29

只做只读操作：不发任何开关机/风速命令。
用于排查集成无法连接设备的问题。
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "air_352_x50s"))

import importlib.util
import types

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


protocol = _load("protocol")

TARGET_IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.0.29"
PORT = 11530
ALL_MAC = "FFFFFFFFFFFF"

seen = []
lock = threading.Lock()


def hx(data: bytes) -> str:
    return data.hex(" ").upper()


def describe(data: bytes, addr):
    header = protocol.parse_header(data)
    line = f"[{addr[0]}:{addr[1]}] len={len(data)}  {hx(data)}"
    if header is None:
        return line + "\n    不是 0xA1 帧"
    info = (
        f"\n    MAC={header['mac']} company=0x{header['company']:02X} "
        f"type=0x{header['device_type']:02X} auth=0x{header['auth']:04X} "
        f"seq={header['seq']} flags=0x{header['flags']:02X} LEN={header['length']}"
    )
    proto = protocol.detect_protocol(header["content"])
    info += f"\n    content[0]=0x{header['content'][0]:02X} 内层={'F0 72' if proto == protocol.PROTOCOL_F072 else ('A5 A0' if proto == protocol.PROTOCOL_A5A0 else '无')}"
    search = protocol.parse_search_response(data)
    if search:
        info += f"\n    搜索应答: ip={search['ip']} mac={search['mac']} type=0x{search['device_type']:02X}"
    state = protocol.parse_state(data, proto or protocol.PROTOCOL_F072)
    if state:
        info += (
            f"\n    状态: power={state['power']} speed={state['speed']} "
            f"mode={state['mode']} pm25={state['pm25']} temp={state['temperature']} "
            f"hum={state['humidity']} co2={state['co2']} filter={state['filter_type']}"
        )
    return line + info


def receiver(sock, stop_event):
    sock.settimeout(0.5)
    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            break
        with lock:
            seen.append((time.time(), addr, data))
        print(describe(data, addr), flush=True)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass

    try:
        sock.bind(("0.0.0.0", PORT))
        print(f"已监听 0.0.0.0:{PORT}")
    except OSError as err:
        print(f"绑定 {PORT} 失败: {err}")
        sock.bind(("0.0.0.0", 0))
        print(f"改用临时端口 {sock.getsockname()[1]}")

    stop = threading.Event()
    thread = threading.Thread(target=receiver, args=(sock, stop), daemon=True)
    thread.start()

    print("\n=== 阶段 1：被动监听 8 秒 ===")
    time.sleep(8)
    if not seen:
        print("（没有收到任何数据）")

    print("\n=== 阶段 2：广播搜索（AUTH=0xCB76） ===")
    for auth, label in [(0xCB76, "APP码CB76"), (0x0504, "旧集成码0504")]:
        seq = 1
        packet = protocol.build_search_frame(ALL_MAC, 0xF1, 0x03, auth, seq)
        print(f"发送 [{label}] -> 255.255.255.255:{PORT}  {hx(packet)}")
        sock.sendto(packet, ("255.255.255.255", PORT))
        time.sleep(1.5)

    print("\n=== 阶段 3：单播搜索到目标 IP ===")
    for auth, label in [(0xCB76, "APP码CB76"), (0x0504, "旧集成码0504")]:
        packet = protocol.build_search_frame(ALL_MAC, 0xF1, 0x03, auth, 2)
        print(f"发送 [{label}] -> {TARGET_IP}:{PORT}  {hx(packet)}")
        sock.sendto(packet, (TARGET_IP, PORT))
        time.sleep(1.5)

    print("\n=== 阶段 4：再等 5 秒 ===")
    time.sleep(5)

    stop.set()
    thread.join(timeout=2)
    sock.close()

    print(f"\n=== 共收到 {len(seen)} 个包 ===")
    if not seen:
        print("设备没有任何回应。可能原因：")
        print("  1. 设备未连入当前网络（检查 App 里是否在线）")
        print("  2. 设备只接受带正确 MAC 的帧")
        print("  3. 路由器隔离了无线客户端")
        print("  4. 需要先用已知 MAC 唤醒")


if __name__ == "__main__":
    main()
