"""Valve platform for the JUDO i-soft plus integration (waterstop)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import JudoError
from .const import DOMAIN, KEY_WS_VALVE

if TYPE_CHECKING:
    from .coordinator import JudoConfigEntry, JudoCoordinator

# Write commands must not run in parallel against the slow embedded
# controller.
PARALLEL_UPDATES = 1

# Tolerant mapping of the device's status strings.
_CLOSED_STATES = frozenset({"close", "closed"})
_OPEN_STATES = frozenset({"open", "opened"})
_CLOSING_STATES = frozenset({"closing"})
_OPENING_STATES = frozenset({"opening"})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JudoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the JUDO waterstop valve from a config entry."""
    async_add_entities([JudoWaterstopValve(entry.runtime_data, entry)])


class JudoWaterstopValve(CoordinatorEntity["JudoCoordinator"], ValveEntity):
    """Controllable waterstop valve of the i-soft plus."""

    _attr_has_entity_name = True
    _attr_translation_key = "waterstop_valve"
    _attr_device_class = ValveDeviceClass.WATER
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
    _attr_reports_position = False

    def __init__(self, coordinator: JudoCoordinator, entry: JudoConfigEntry) -> None:
        """Initialize the valve."""
        super().__init__(coordinator)
        self._attr_unique_id = f"judo_{entry.entry_id}_waterstop_valve"
        # Attach to the same device as the sensors.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _raw_state(self) -> str | None:
        data = self.coordinator.data or {}
        value = data.get(KEY_WS_VALVE)
        return value.strip().lower() if isinstance(value, str) else None

    @property
    def available(self) -> bool:
        """Only available if the last poll produced a valve status."""
        return super().available and KEY_WS_VALVE in (self.coordinator.data or {})

    @property
    def is_closed(self) -> bool | None:
        """Return True if the valve is closed, None if unknown."""
        state = self._raw_state()
        if state in _CLOSED_STATES:
            return True
        if state in _OPEN_STATES:
            return False
        return None

    @property
    def is_closing(self) -> bool:
        """Return True while the valve is closing."""
        return self._raw_state() in _CLOSING_STATES

    @property
    def is_opening(self) -> bool:
        """Return True while the valve is opening."""
        return self._raw_state() in _OPENING_STATES

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_open_valve(self) -> None:
        """Open the waterstop valve."""
        await self._async_write("open")

    async def async_close_valve(self) -> None:
        """Close the waterstop valve."""
        await self._async_write("close")

    async def _async_write(self, parameter: str) -> None:
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.api.write_value, "waterstop", "valve", parameter
            )
        except (OSError, JudoError, ValueError) as err:
            raise HomeAssistantError(
                f"Could not send '{parameter}' to the waterstop valve: {err}"
            ) from err
        # Fetch the real state right away (debounced).
        await self.coordinator.async_request_refresh()
