"""Sensor platform for the JUDO i-soft plus integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfMass,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SERIAL,
    DOMAIN,
    KEY_HW_VERSION,
    KEY_SW_VERSION,
    KEY_WATER_TOTAL_LIVE,
)

if TYPE_CHECKING:
    from .coordinator import DataKey, JudoConfigEntry, JudoCoordinator

# The device is a slow embedded controller; the coordinator already reads
# values sequentially, entities must not trigger parallel updates on top.
PARALLEL_UPDATES = 0

# The device reports flow rates in litres per hour, which is not a valid
# unit for SensorDeviceClass.VOLUME_FLOW_RATE - so those sensors carry the
# raw unit without a device class.
LITERS_PER_HOUR = "L/h"
HARDNESS_DH = "°dH"


@dataclass(frozen=True, kw_only=True)
class JudoSensorEntityDescription(SensorEntityDescription):
    """Describes a JUDO sensor and where its value comes from."""

    api_group: str
    api_command: str


SENSOR_DESCRIPTIONS: tuple[JudoSensorEntityDescription, ...] = (
    # ------------------------------------------------------------------
    # The only sensor enabled by default: hourly total + intra-hour value
    # combined by the coordinator into a live, monotonic total in m³.
    # ------------------------------------------------------------------
    JudoSensorEntityDescription(
        key="water_total_live",
        translation_key="water_total_live",
        api_group="internal",
        api_command="water_total_live",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    ),
    # ------------------------------------------------------------------
    # Raw water counters (default disabled)
    # ------------------------------------------------------------------
    JudoSensorEntityDescription(
        key="water_total",
        translation_key="water_total",
        api_group="consumption",
        api_command="water%20total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="water_current",
        translation_key="water_current",
        api_group="consumption",
        api_command="water%20current",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="water_daily",
        translation_key="water_daily",
        api_group="consumption",
        api_command="water%20daily",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="water_weekly",
        translation_key="water_weekly",
        api_group="consumption",
        api_command="water%20weekly",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="water_monthly",
        translation_key="water_monthly",
        api_group="consumption",
        api_command="water%20monthly",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="water_yearly",
        translation_key="water_yearly",
        api_group="consumption",
        api_command="water%20yearly",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    # ------------------------------------------------------------------
    # Operating values (default disabled)
    # ------------------------------------------------------------------
    JudoSensorEntityDescription(
        key="flow_rate",
        translation_key="flow_rate",
        api_group="consumption",
        api_command="actual%20flow%20rate",
        native_unit_of_measurement=LITERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="actual_quantity",
        translation_key="actual_quantity",
        api_group="consumption",
        api_command="actual%20quantity",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cup-water",
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="salt_quantity",
        translation_key="salt_quantity",
        api_group="consumption",
        api_command="salt%20quantity",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:shaker-outline",
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="salt_range",
        translation_key="salt_range",
        api_group="consumption",
        api_command="salt%20range",
        native_unit_of_measurement=UnitOfTime.DAYS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="residual_hardness",
        translation_key="residual_hardness",
        api_group="settings",
        api_command="residual%20hardness",
        native_unit_of_measurement=HARDNESS_DH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="natural_hardness",
        translation_key="natural_hardness",
        api_group="info",
        api_command="natural%20hardness",
        native_unit_of_measurement=HARDNESS_DH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        entity_registry_enabled_default=False,
    ),
    # ------------------------------------------------------------------
    # Waterstop status (default disabled)
    # ------------------------------------------------------------------
    JudoSensorEntityDescription(
        key="valve",
        translation_key="valve",
        api_group="waterstop",
        api_command="valve",
        icon="mdi:valve",
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="vacation",
        translation_key="vacation",
        api_group="waterstop",
        api_command="vacation",
        icon="mdi:beach",
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="ws_standby",
        translation_key="ws_standby",
        api_group="waterstop",
        api_command="standby",
        icon="mdi:power-standby",
        entity_registry_enabled_default=False,
    ),
    # ------------------------------------------------------------------
    # Waterstop limits -> diagnostic entities (default disabled)
    # ------------------------------------------------------------------
    JudoSensorEntityDescription(
        key="abstraction_time",
        translation_key="abstraction_time",
        api_group="waterstop",
        api_command="abstraction%20time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="flow_rate_limit",
        translation_key="flow_rate_limit",
        api_group="waterstop",
        api_command="flow%20rate",
        native_unit_of_measurement=LITERS_PER_HOUR,
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    JudoSensorEntityDescription(
        key="quantity_limit",
        translation_key="quantity_limit",
        api_group="waterstop",
        api_command="quantity",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        icon="mdi:water-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JudoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up JUDO sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        JudoSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    )


class JudoSensor(CoordinatorEntity["JudoCoordinator"], SensorEntity):
    """Sensor backed by the shared JUDO coordinator."""

    entity_description: JudoSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JudoCoordinator,
        description: JudoSensorEntityDescription,
        entry: JudoConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"judo_{entry.entry_id}_{description.key}"

        # Where this sensor's value lives in coordinator.data.
        self._data_key: DataKey = (
            KEY_WATER_TOTAL_LIVE
            if description.api_group == "internal"
            else (description.api_group, description.api_command)
        )

        data = coordinator.data or {}
        sw_version = data.get(KEY_SW_VERSION)
        hw_version = data.get(KEY_HW_VERSION)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="JUDO i-soft plus",
            manufacturer="JUDO",
            model="i-soft plus",
            serial_number=entry.data.get(CONF_SERIAL),
            sw_version=str(sw_version) if sw_version is not None else None,
            hw_version=str(hw_version) if hw_version is not None else None,
        )

    async def async_added_to_hass(self) -> None:
        """Request a refresh if our value has not been polled yet.

        The coordinator only polls values belonging to enabled entities.
        When a sensor is enabled later, its value is not in the data yet;
        trigger one (debounced) refresh so it fills in right away instead
        of staying unavailable for a full scan interval.
        """
        await super().async_added_to_hass()
        if self._data_key not in (self.coordinator.data or {}):
            await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        """Only available if the last poll produced a value for us."""
        return super().available and self._data_key in (self.coordinator.data or {})

    @property
    def native_value(self) -> Any:
        """Return the current value from the coordinator."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)
