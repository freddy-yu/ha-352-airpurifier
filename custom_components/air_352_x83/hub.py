"""352 设备通信中枢：帧收发、状态解析、认证码学习。"""

from __future__ import annotations

import asyncio
import logging
import socket
import time

from . import protocol
from .const import (
    APP_AUTH_CODE,
    COMPANY_CODE_LRD,
    DEFAULT_DEVICE_AUTH,
    UDP_PORT,
    commands_for,
    model_info,
)

_LOGGER = logging.getLogger(__name__)

BROADCAST_ADDRESS = "255.255.255.255"
ALL_DEVICE_MAC = "FFFFFFFFFFFF"


class Air352Hub:
    """单个 352 设备的本地 UDP 会话。"""

    def __init__(self, hass, host, mac, model="x50s", auth=None, company=None):
        self.hass = hass
        self.host = host
        self.mac = mac.replace(":", "").replace("-", "").upper()
        self.model = (model or "x50s").lower()
        self.info = model_info(self.model)

        self.device_type = self.info["device_type"]
        self.protocol = self.info["protocol"]
        self.speed_count = self.info["speed_count"]
        self.commands = commands_for(self.model)

        self.company = company if company is not None else COMPANY_CODE_LRD
        self.auth = auth if auth is not None else DEFAULT_DEVICE_AUTH
        # 用户显式配置过认证码时不再试图“学习”，避免被应答里的回显覆盖
        self._auth_explicit = auth is not None

        self._seq = 0
        self._callbacks = set()
        self._transport = None
        self.last_seen = 0.0
        self.available = False

        self.status = {
            "power": False,
            "speed": 0,
            "mode": None,
            "light": True,
            "pm25": 0,
            "temperature": None,
            "humidity": None,
            "co2": None,
            "filter_type": None,
            "filter_warning": None,
            "child_lock": False,
            "timer": 0,
            "ptc": 0,
            "air_quality": 0,
            "total_purification": 0,
            "cumulative_purification": 0,
            "total_online_time": 0,
        }

    # ------------------------------------------------------------------
    # 回调
    # ------------------------------------------------------------------

    def register_callback(self, callback):
        self._callbacks.add(callback)

    def remove_callback(self, callback):
        self._callbacks.discard(callback)

    def _notify(self):
        for callback in list(self._callbacks):
            try:
                callback()
            except Exception:  # noqa: BLE001 - 单个实体异常不应拖垮解析
                _LOGGER.exception("状态回调执行失败")

    # ------------------------------------------------------------------
    # 序号
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) % 32768
        return self._seq

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------

    async def _async_send(self, packet: bytes, broadcast: bool = False) -> bool:
        if not packet:
            return False

        def _send() -> bool:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    target = BROADCAST_ADDRESS if broadcast else self.host
                    sock.sendto(packet, (target, UDP_PORT))
                return True
            except OSError as err:
                _LOGGER.warning("发送 UDP 数据失败: %s", err)
                return False

        return await asyncio.get_running_loop().run_in_executor(None, _send)

    def _build_command(self, p5: int, p6: int) -> bytes:
        seq = self._next_seq()
        if self.protocol == protocol.PROTOCOL_A5A0:
            return protocol.build_a5a0_command(
                self.mac, self.company, self.device_type, self.auth, seq, p5, p6
            )
        return protocol.build_f072_command(
            self.mac, self.company, self.device_type, self.auth, seq, p5, p6
        )

    async def async_control(self, action: str) -> bool:
        if action in self.info.get("unsupported", []):
            _LOGGER.warning("%s 型号不支持命令: %s", self.model, action)
            return False

        params = self.commands.get(action)
        if params is None:
            _LOGGER.warning("未知命令: %s", action)
            return False

        p5, p6 = params
        packet = self._build_command(p5, p6)
        _LOGGER.debug("发送 %s -> %s", action, packet.hex(" ").upper())
        return await self._async_send(packet)

    # 兼容旧接口名
    async_send_command = async_control

    async def async_query(self) -> bool:
        return await self.async_control("query")

    async def async_heartbeat(self) -> bool:
        seq = self._next_seq()
        packet = protocol.build_heartbeat_frame(
            self.mac, self.company, self.device_type, self.auth, seq
        )
        return await self._async_send(packet)

    async def async_discover(self) -> bool:
        """搜索设备，用于确认在线并学习真实认证码。

        实测 X50S 不回应 IPv4 广播（255.255.255.255），但回应单播。
        所以先广播（兼容其它型号/未知 IP），再单播一次（X50S 实际依赖这条）。
        """
        seq = self._next_seq()
        packet = protocol.build_search_frame(
            self.mac, COMPANY_CODE_LRD, self.device_type, APP_AUTH_CODE, seq
        )
        _LOGGER.debug("搜索 -> %s", packet.hex(" ").upper())
        sent = await self._async_send(packet, broadcast=True)

        if self.host and self.host not in ("", "0.0.0.0"):
            sent = await self._async_send(packet) or sent
        return sent

    # ------------------------------------------------------------------
    # 接收
    # ------------------------------------------------------------------

    def parse_data(self, data: bytes, addr=None) -> bool:
        header = protocol.parse_header(data)
        if header is None:
            return False

        # 只接受本设备或广播帧
        if header["mac"] not in (self.mac, ALL_DEVICE_MAC):
            return False

        self._learn_identity(header)

        content = header["content"]
        if content and content[0] == protocol.CMD_SEARCH:
            response = protocol.parse_search_response(data)
            if response:
                _LOGGER.debug("发现设备 %s @ %s", response["mac"], response["ip"])
                if not self.host or self.host in ("", "0.0.0.0"):
                    self.host = response["ip"]
            self._mark_online()
            return True

        if content and content[0] == protocol.CMD_HEARTBEAT:
            interval = protocol.parse_heartbeat_response(data)
            if interval:
                _LOGGER.debug("设备心跳间隔 %ss", interval)
            self._mark_online()
            return True

        warning = protocol.parse_filter_warning(data)
        if warning is not None:
            self.status["filter_warning"] = warning
            self._mark_online()
            self._notify()
            return True

        detected = protocol.detect_protocol(content)
        state = protocol.parse_state(data, detected or self.protocol)
        if state is None:
            return False

        self._apply_state(state)
        self._mark_online()
        self._notify()
        return True

    def _learn_identity(self, header: dict) -> None:
        """从收到的帧里学习厂商码/设备类型/认证码。

        App 也是这样做的：把帧头 [12..15] 直接写回设备记录。
        但应答帧可能把请求里的 APP 认证码原样回显，所以排除 0xCB76；
        用户显式配置过 auth 时也不覆盖。
        """
        company = header["company"]
        auth = header["auth"]
        device_type = header["device_type"]

        changed = False
        if company not in (0x00, 0xFF) and company != self.company:
            self.company = company
            changed = True
        if (
            not self._auth_explicit
            and auth not in (0x0000, 0xFFFF, APP_AUTH_CODE)
            and auth != self.auth
        ):
            self.auth = auth
            changed = True
        if device_type not in (0x00, 0xFF) and device_type != self.device_type:
            _LOGGER.info(
                "设备上报类型 0x%02X 与配置 0x%02X 不同，改用上报值",
                device_type,
                self.device_type,
            )
            self.device_type = device_type
            changed = True
        if changed:
            _LOGGER.debug(
                "更新设备身份: company=0x%02X type=0x%02X auth=0x%04X",
                self.company,
                self.device_type,
                self.auth,
            )

    def _apply_state(self, state: dict) -> None:
        """设备上报就是真相，直接采用。

        曾试过模仿 App 在命令后锁定 3 秒不透传上报，但那会丢掉
        设备真实的关机/调速回帧，导致状态永久错误。乐观更新交给实体层，
        这里只负责反映设备真实状态。
        """
        self.status.update(state)

    def _mark_online(self) -> None:
        self.last_seen = time.monotonic()
        if not self.available:
            self.available = True
            _LOGGER.info("%s 已上线", self.mac)
            self._notify()

    def check_availability(self, timeout: float = 60.0) -> bool:
        """超过 timeout 没收到任何帧就认为离线。"""
        if not self.last_seen:
            return self.available
        if time.monotonic() - self.last_seen > timeout:
            if self.available:
                self.available = False
                _LOGGER.info("%s 已离线", self.mac)
                self._notify()
        return self.available

    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        return self.info["name"]
