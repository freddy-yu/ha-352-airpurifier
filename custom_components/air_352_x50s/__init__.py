"""352 空气净化器集成入口。"""

from __future__ import annotations

import asyncio
import logging
import socket
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, HEARTBEAT_INTERVAL, QUERY_INTERVAL, UDP_PORT
from .hub import Air352Hub

_LOGGER = logging.getLogger(__name__)

SHARED_KEY = "_shared"
PLATFORMS = ["fan", "sensor", "light", "select"]


class SharedUdpProtocol(asyncio.DatagramProtocol):
    """所有设备共用一个 UDP 监听端口，按 MAC 分发。"""

    def __init__(self, store: dict):
        self._store = store

    def datagram_received(self, data, addr):
        for key, hub in list(self._store.items()):
            if key.startswith("_") or not isinstance(hub, Air352Hub):
                continue
            try:
                hub.parse_data(data, addr)
            except Exception:  # noqa: BLE001 - 单个设备解析异常不影响其它设备
                _LOGGER.exception("解析设备 %s 的数据失败", hub.mac)


async def _async_ensure_socket(hass: HomeAssistant):
    """创建（或复用）共享的 UDP 监听套接字。"""
    store = hass.data.setdefault(DOMAIN, {})
    shared = store.get(SHARED_KEY)
    if shared is not None:
        return shared

    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass

    try:
        sock.bind(("0.0.0.0", UDP_PORT))
    except OSError as err:
        _LOGGER.warning(
            "端口 %s 被占用（%s），改用临时端口；设备主动广播可能收不到，"
            "但应答仍可回到本端口",
            UDP_PORT,
            err,
        )
        sock.bind(("0.0.0.0", 0))

    transport, _ = await loop.create_datagram_endpoint(
        lambda: SharedUdpProtocol(store), sock=sock
    )
    store[SHARED_KEY] = transport
    return transport


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    data = entry.data
    hub = Air352Hub(
        hass,
        host=data.get("host"),
        mac=data.get("mac"),
        model=data.get("model", "x50s"),
        auth=data.get("auth"),
        company=data.get("company"),
    )

    try:
        await _async_ensure_socket(hass)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("无法创建 UDP 监听: %s", err)
        return False

    store = hass.data.setdefault(DOMAIN, {})
    store[entry.entry_id] = hub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_tick(_now=None):
        # 先尝试搜索（可学习真实认证码），再发心跳保活
        if not hub.available:
            await hub.async_discover()
        await hub.async_heartbeat()
        hub.check_availability()

    async def _async_query(_now=None):
        await hub.async_query()

    entry.async_on_unload(
        async_track_time_interval(
            hass, _async_tick, timedelta(seconds=HEARTBEAT_INTERVAL)
        )
    )
    entry.async_on_unload(
        async_track_time_interval(hass, _async_query, timedelta(seconds=QUERY_INTERVAL))
    )

    hass.async_create_task(hub.async_discover())
    hass.async_create_task(hub.async_query())
    return True


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    store = hass.data.get(DOMAIN, {})
    store.pop(entry.entry_id, None)

    remaining = [k for k in store if not k.startswith("_")]
    if not remaining:
        transport = store.pop(SHARED_KEY, None)
        if transport is not None:
            transport.close()

    return True
