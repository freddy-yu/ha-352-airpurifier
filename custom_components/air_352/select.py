"""352 空气净化器模式选择实体。

HA 的 fan 实体虽然支持 preset_mode，但默认卡片（tile card）不会渲染
模式下拉框，需要在卡片上手动添加功能才看得到。这里额外提供一个
select 实体，让模式选择在任何卡片和自动化里都直接可用。
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DOMAIN, PRESET_MODES


async def async_setup_entry(hass, config_entry, async_add_entities):
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([Air352ModeSelect(hub)])


class Air352ModeSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "运行模式"
    _attr_icon = "mdi:fan-auto"
    _attr_options = list(PRESET_MODES)
    _attr_translation_key = "mode"

    def __init__(self, hub):
        self._hub = hub
        self._attr_unique_id = f"select_{hub.mac}_mode"

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
        # 关机时选模式会自动开机，所以保持可用
        return self._hub.available

    async def async_added_to_hass(self):
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.async_write_ha_state)

    @property
    def current_option(self):
        mode = self._hub.status.get("mode")
        return mode if mode in PRESET_MODES else None

    async def async_select_option(self, option: str) -> None:
        if option not in PRESET_MODES:
            return
        await self._hub.async_set_mode(option)
