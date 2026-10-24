"""验证 sensor 实体正确读取 hub 的 speed 字段。"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "air_352"
FAILS = []


def check(label, actual, expected):
    if actual != expected:
        FAILS.append(f"{label}: 实际 {actual!r} 期望 {expected!r}")
        print(f"FAIL {label}")
    else:
        print(f"ok   {label}")


class FakeSensor:
    _attr_has_entity_name = False
    _attr_name = None
    _attr_unique_id = None
    _attr_icon = None
    _attr_native_unit_of_measurement = None
    _attr_device_class = None
    _attr_state_class = None
    _attr_entity_category = None

    def async_write_ha_state(self):
        pass


class FakeDeviceClass:
    PM25 = "pm25"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    CO2 = "co2"


class FakeStateClass:
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"


class FakeEntityCategory:
    DIAGNOSTIC = "diagnostic"


class FakeUnitOfTemp:
    CELSIUS = "°C"


def _install():
    mods = {
        "homeassistant": types.ModuleType("homeassistant"),
        "homeassistant.components": types.ModuleType("homeassistant.components"),
        "homeassistant.components.sensor": types.ModuleType("homeassistant.components.sensor"),
        "homeassistant.const": types.ModuleType("homeassistant.const"),
        "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.entity": types.ModuleType("homeassistant.helpers.entity"),
    }
    sm = mods["homeassistant.components.sensor"]
    sm.SensorEntity = FakeSensor
    sm.SensorDeviceClass = FakeDeviceClass
    sm.SensorStateClass = FakeStateClass
    c = mods["homeassistant.const"]
    c.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER = "µg/m³"
    c.PERCENTAGE = "%"
    c.UnitOfTemperature = FakeUnitOfTemp
    mods["homeassistant.helpers.entity"].EntityCategory = FakeEntityCategory

    sys.modules.update(mods)
    pkg = types.ModuleType("air352")
    pkg.__path__ = [str(COMP_DIR)]
    sys.modules["air352"] = pkg


_install()


def _load(name):
    spec = importlib.util.spec_from_file_location(f"air352.{name}", COMP_DIR / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"air352.{name}"] = m
    spec.loader.exec_module(m)
    return m


const = _load("const")
sensormod = _load("sensor")


class FakeHub:
    mac = "F0FE6B9388FF"
    model = "x50s"
    display_name = "352 X50S"
    available = True

    def __init__(self, speed=1, mode="auto"):
        self.status = {
            "pm25": 12,
            "speed": speed,
            "mode": mode,
            "cumulative_purification": 405140,
            "filter_type": "standard",
            "total_purification": 0,
        }

    def register_callback(self, cb):
        pass

    def remove_callback(self, cb):
        pass


print("=== sensor.speed 随档位变化 ===")
for gear in (1, 2, 3, 4, 5, 6):
    hub = FakeHub(speed=gear)
    sensors = [sensormod.Air352Sensor(hub, *d) for d in sensormod.BASE_SENSORS]
    speed_sensor = next(s for s in sensors if s._key == "speed")
    print(f"   hub.status['speed']={gear} -> native_value={speed_sensor.native_value}")
    check(f"档位 {gear} 正确读出", speed_sensor.native_value, gear)

print("\n=== 其它传感器 ===")
hub = FakeHub()
sensors = {s._key: s for s in (sensormod.Air352Sensor(hub, *d) for d in sensormod.BASE_SENSORS)}
check("PM2.5", sensors["pm25"].native_value, 12)
check("累计净化量", sensors["cumulative_purification"].native_value, 405140)
check("滤芯状态", sensors["filter_type"].native_value, "standard")

print("\n=== 缺少字段时返回 None（HA 显示 unknown）===")
hub2 = FakeHub()
del hub2.status["speed"]
s2 = sensormod.Air352Sensor(hub2, *sensormod.BASE_SENSORS[1])
check("缺失字段返回 None", s2.native_value, None)

print()
if FAILS:
    print(f"=== {len(FAILS)} 项失败 ===")
    for f in FAILS:
        print(" ", f)
    raise SystemExit(1)
print("全部通过 —— sensor 逻辑无误，问题在 UI 入口")
