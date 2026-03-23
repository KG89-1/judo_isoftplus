import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "water_today": ("water_today", "L", "consumption", "water%20daily", False),
    "water_total": ("water_total", "L", "consumption", "water%20total", False),
    "flow_rate": ("flow_rate", "L/h", "consumption", "actual%20flow%20rate", False),
    "actual_quantity": ("actual_quantity", "L", "consumption", "actual%20quantity", False),
    "salt_quantity": ("salt_quantity", "g", "consumption", "salt%20quantity", False),
    "salt_range": ("salt_range", "days", "consumption", "salt%20range", False),
    "residual_hardness": ("residual_hardness", "°dH", "settings", "residual%20hardness", False),
    "natural_hardness": ("natural_hardness", "°dH", "info", "natural%20hardness", False),
    "valve": ("valve", None, "waterstop", "valve", False),
    "vacation": ("vacation", None, "waterstop", "vacation", False),
    "abstraction_time": ("abstraction_time","min","waterstop","abstraction%20time",False),
    "flow_rate_limit": ("flow_rate_limit", "L/h", "waterstop", "flow%20rate", False),
    "quantity_limit": ("quantity_limit", "L", "waterstop", "quantity", False),

    # Multi-interval consumption sensors (all default disabled)
    "water_current": ("water_current", "L", "consumption", "water%20current", False),
    "water_daily": ("water_daily", "L", "consumption", "water%20daily", False),
    "water_weekly": ("water_weekly", "L", "consumption", "water%20weekly", False),
    "water_monthly": ("water_monthly", "L", "consumption", "water%20monthly", False),
    "water_yearly": ("water_yearly", "L", "consumption", "water%20yearly", False),

    # The ONLY default-enabled sensor
    "water_total_live": ("water_total_live", "m³", "internal", "water_total_live", True),

    "ws_standby": ("ws_standby", None, "waterstop", "standby", False),
}

HIDDEN_SENSOR_TYPES = {
    "software_version": ("version", "software%20version"),
    "hardware_version": ("version", "hardware%20version"),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []

    for sensor_id, (translation_key, unit, group, command, default_enabled) in SENSOR_TYPES.items():
        entities.append(
            JudoSensor(
                coordinator,
                sensor_id,
                translation_key,
                unit,
                group,
                command,
                default_enabled,
                entry.entry_id,
                entry.data.get("serial"),
            )
        )

    async_add_entities(entities)


class JudoSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        coordinator,
        sensor_id,
        translation_key,
        unit,
        group,
        command,
        default_enabled,
        entry_id,
        serial_number,
    ):
        super().__init__(coordinator)

        self.entry_id = entry_id
        self._serial_number = serial_number

        self._attr_translation_key = translation_key
        self._attr_unique_id = f"judo_{entry_id}_{sensor_id}"
        self._attr_native_unit_of_measurement = unit
        self._attr_has_entity_name = True
        self._attr_entity_registry_enabled_default = default_enabled
        self._group = group
        self._command = command

        # Only the live water sensor uses device_class
        if sensor_id == "water_total_live":
            self._attr_device_class = "water"
            self._attr_state_class = "total_increasing"

        # Normal total WITHOUT device_class so HA doesn't auto-enable it
        elif sensor_id == "water_total":
            self._attr_state_class = "total_increasing"

    @property
    def native_value(self):
        return self.coordinator.data.get((self._group, self._command))

    @property
    def device_info(self):
        data = self.coordinator.data
        return {
            "identifiers": {(DOMAIN, self.entry_id)},
            "name": "JUDO i-soft plus",
            "manufacturer": "JUDO",
            "model": "i-soft plus",
            "sw_version": data.get(("version", "software%20version")),
            "hw_version": data.get(("version", "hardware%20version")),
            "serial_number": self._serial_number,
        }
