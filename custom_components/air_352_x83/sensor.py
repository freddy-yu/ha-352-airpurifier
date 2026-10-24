"""352 空气净化器传感器实体。"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, model_info

BASE_SENSORS = [
    ("pm25", "PM2.5", CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "mdi:air-filter",
     SensorDeviceClass.PM25, SensorStateClass.MEASUREMENT),
    ("speed", "风速档位", None, "mdi:fan-speed-1", None, None),
    # X50S 实测有值的是 cumulative_purification（body[24..26]）；
    # total_purification 在 X50S 上恒为 0，作为诊断传感器单独保留
    ("cumulative_purification", "累计净化空气量", "m³", "mdi:leaf-circle-outline",
     None, SensorStateClass.TOTAL_INCREASING),
    ("filter_type", "滤芯状态", None, "mdi:filter-check-outline", None, None),
]

EXTRA_SENSORS = {
    "temperature": ("temperature", "温度", UnitOfTemperature.CELSIUS, "mdi:thermometer",
                    SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    "humidity": ("humidity", "湿度", PERCENTAGE, "mdi:water-percent",
                 SensorDeviceClass.HUMIDITY, SensorStateClass.MEASUREMENT),
    "co2": ("co2", "CO2", "ppm", "mdi:molecule-co2",
            SensorDeviceClass.CO2, SensorStateClass.MEASUREMENT),
    "filter_warning": ("filter_warning", "滤芯预警", PERCENTAGE, "mdi:filter-alert",
                       None, SensorStateClass.MEASUREMENT),
    "total_purification": ("total_purification", "累计运行空气量", "m³",
                           "mdi:counter", None, None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    info = model_info(hub.model)

    entities = [Air352Sensor(hub, *desc) for desc in BASE_SENSORS]
    for key in info.get("extra_sensors", []):
        desc = EXTRA_SENSORS.get(key)
        if desc:
            entities.append(Air352Sensor(hub, *desc))

    entities.append(Air352Sensor(hub, *EXTRA_SENSORS["total_purification"]))

    async_add_entities(entities)


class Air352Sensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, hub, key, name, unit, icon, device_class, state_class):
        self._hub = hub
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"sensor_{hub.mac}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        if key in ("filter_type", "filter_warning", "total_purification"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

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
    def native_value(self):
        return self._hub.status.get(self._key)
