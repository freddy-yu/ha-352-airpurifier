"""352 空气净化器风扇实体。"""

from __future__ import annotations

import asyncio

from homeassistant.components.fan import FanEntity, FanEntityFeature

from .const import DOMAIN, PRESET_MODES


async def async_setup_entry(hass, config_entry, async_add_entities):
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([Air352FanEntity(hub)])


class Air352FanEntity(FanEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, hub):
        self._hub = hub
        self._attr_unique_id = f"fan_{hub.mac}"
        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED
            | FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
            | FanEntityFeature.PRESET_MODE
        )
        self._attr_speed_count = hub.speed_count
        self._attr_preset_modes = list(PRESET_MODES)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._hub.mac)},
            "name": self._hub.display_name,
            "manufacturer": "352",
            "model": self._hub.display_name,
        }

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self._hub.available

    async def async_added_to_hass(self):
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.async_write_ha_state)

    @property
    def is_on(self):
        return bool(self._hub.status.get("power"))

    @property
    def percentage(self):
        speed = self._hub.status.get("speed") or 0
        count = self._hub.speed_count
        if speed <= 0:
            return 0
        return min(100, round(speed / count * 100))

    @property
    def preset_mode(self):
        mode = self._hub.status.get("mode")
        return mode if mode in PRESET_MODES else None

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        self._hub.status["power"] = True
        self.async_write_ha_state()
        await self._hub.async_control("on")

        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        elif percentage:
            await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs):
        self._hub.status["power"] = False
        self.async_write_ha_state()
        await self._hub.async_control("off")

    async def async_set_percentage(self, percentage: int):
        if percentage == 0:
            await self.async_turn_off()
            return

        count = self._hub.speed_count
        speed = max(1, min(count, round(percentage / 100 * count)))
        was_on = bool(self._hub.status.get("power"))
        self._hub.status["power"] = True
        self._hub.status["speed"] = speed
        self.async_write_ha_state()

        if not was_on:
            await self._hub.async_control("on")
            # 同上：等设备开机初始化稳定后再调风速
            await asyncio.sleep(0.8)
        await self._hub.async_control(f"speed_{speed}")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in PRESET_MODES:
            return
        # 设备关机时模式命令会被忽略，必须先开机
        was_on = bool(self._hub.status.get("power"))
        self._hub.status["power"] = True
        self._hub.status["mode"] = preset_mode
        self.async_write_ha_state()

        if not was_on:
            await self._hub.async_control("on")
            # 设备开机后有一段初始化（风速会自己跳几下），
            # 紧跟的命令可能被覆盖，留出稳定时间。
            await asyncio.sleep(0.8)
        await self._hub.async_control(preset_mode)
