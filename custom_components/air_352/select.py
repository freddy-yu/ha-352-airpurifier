"""352 空气净化器的下拉选择实体：运行模式 + 风速档位。

HA 的 fan 实体本身支持 preset_mode 和 percentage，但默认卡片（tile card）
不渲染模式下拉框，也不渲染风速滑块，需要在卡片上手动添加功能才看得到。
这两个 select 实体把入口显式暴露出来，任何卡片、自动化、语音助手都能用。
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DOMAIN, PRESET_MODES


async def async_setup_entry(hass, config_entry, async_add_entities):
    hub = hass.data[DOMAIN][config_entry.entry_id]
    entities = [Air352ModeSelect(hub)]
    # X83 等 6 档机型也走同一套逻辑
    if hub.speed_count > 1:
        entities.append(Air352SpeedSelect(hub))
    async_add_entities(entities)


class _Air352SelectBase(SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, hub):
        self._hub = hub

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
        # 关机时选择会自动先开机，所以保持可用
        return self._hub.available

    async def async_added_to_hass(self):
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.async_write_ha_state)


class Air352ModeSelect(_Air352SelectBase):
    _attr_name = "运行模式"
    _attr_icon = "mdi:fan-auto"
    _attr_options = list(PRESET_MODES)
    _attr_translation_key = "mode"

    def __init__(self, hub):
        super().__init__(hub)
        self._attr_unique_id = f"select_{hub.mac}_mode"

    @property
    def current_option(self):
        mode = self._hub.status.get("mode")
        return mode if mode in PRESET_MODES else None

    async def async_select_option(self, option: str) -> None:
        if option not in PRESET_MODES:
            return
        await self._hub.async_set_mode(option)


class Air352SpeedSelect(_Air352SelectBase):
    """风速档位。

    档位是设备当前实际风速，不是「设定值」：自动和睡眠模式下由设备自己
    决定（通常是最低档），手动模式下才是用户选的那一档。极速模式设备会
    跑到超出常规档位的数值，此时返回 None（选项里没有该值）。
    """

    _attr_name = "风速档位"
    _attr_icon = "mdi:fan-speed-2"
    _attr_translation_key = "speed"

    def __init__(self, hub):
        super().__init__(hub)
        self._attr_unique_id = f"select_{hub.mac}_speed"
        self._attr_options = [str(i) for i in range(1, hub.speed_count + 1)]

    @property
    def current_option(self):
        speed = self._hub.status.get("speed")
        if speed is None:
            return None
        value = str(speed)
        return value if value in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        try:
            speed = int(option)
        except (TypeError, ValueError):
            return
        if not 1 <= speed <= self._hub.speed_count:
            return
        await self._hub.async_set_speed(speed)
