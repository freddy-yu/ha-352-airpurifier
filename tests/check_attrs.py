"""检查 fan 实体对外暴露的属性，确认 HA 能否看到 preset/speed 能力。"""

from __future__ import annotations

import enum
import importlib.util
import sys
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352_x50s"


class _Feature(enum.IntFlag):
    TURN_ON = 1
    TURN_OFF = 2
    SET_SPEED = 4
    PRESET_MODE = 8


class FakeEntity:
    _attr_has_entity_name = False
    _attr_name = None
    _attr_unique_id = None
    _attr_supported_features = 0
    _attr_speed_count = None
    _attr_preset_modes = None
    _attr_preset_mode = None

    def async_write_ha_state(self):
        pass


ha = types.ModuleType("homeassistant")
comp = types.ModuleType("homeassistant.components")
fan_mod = types.ModuleType("homeassistant.components.fan")
fan_mod.FanEntity = FakeEntity
fan_mod.FanEntityFeature = _Feature
sys.modules.update({
    "homeassistant": ha,
    "homeassistant.components": comp,
    "homeassistant.components.fan": fan_mod,
})

pkg = types.ModuleType("air352")
pkg.__path__ = [str(COMP_DIR)]
sys.modules["air352"] = pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"air352.{name}", COMP_DIR / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"air352.{name}"] = m
    spec.loader.exec_module(m)
    return m


const = _load("const")
hubmod = _load("hub")
fanmod = _load("fan")


class FakeHub:
    mac = "F0FE6B9388FF"
    model = "x50s"
    info = const.model_info("x50s")
    speed_count = 5
    display_name = "352 X50S"
    available = True
    status = {"power": True, "speed": 3, "mode": "auto", "light": True}


hub = FakeHub()
fan = fanmod.Air352FanEntity(hub)

print("=== 实体对外暴露 ===")
print("supported_features :", fan._attr_supported_features, "=", int(fan._attr_supported_features))
print("  SET_SPEED 位     :", bool(fan._attr_supported_features & _Feature.SET_SPEED))
print("  PRESET_MODE 位   :", bool(fan._attr_supported_features & _Feature.PRESET_MODE))
print("speed_count        :", fan._attr_speed_count)
print("preset_modes       :", fan._attr_preset_modes)
print("preset_mode        :", fan.preset_mode)
print("percentage         :", fan.percentage)
print("is_on              :", fan.is_on)
print()

print("=== 是否有 preset_modes 属性 ===")
print("hasattr preset_modes:", hasattr(fan, "preset_modes"))
print("hasattr speed_count :", hasattr(fan, "speed_count"))
print()

print("=== const.PRESET_MODES ===")
print(const.PRESET_MODES)
