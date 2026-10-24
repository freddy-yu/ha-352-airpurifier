"""352 空气净化器屏幕灯实体。"""

from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity

from .const import DOMAIN


async def async_setup_entry(hass, config_entry, async_add_entities):
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([Air352LightEntity(hub)])


class Air352LightEntity(LightEntity):
    _attr_has_entity_name = True
    _attr_name = "屏幕灯"
    _attr_icon = "mdi:led-on"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(self, hub):
        self._hub = hub
        self._attr_unique_id = f"light_{hub.mac}"

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
        if not self._hub.status.get("power"):
            return False
        return bool(self._hub.status.get("light", False))

    async def async_turn_on(self, **kwargs):
        self._hub.status["light"] = True
        self.async_write_ha_state()
        await self._hub.async_control("light_on")

    async def async_turn_off(self, **kwargs):
        self._hub.status["light"] = False
        self.async_write_ha_state()
        await self._hub.async_control("light_off")
