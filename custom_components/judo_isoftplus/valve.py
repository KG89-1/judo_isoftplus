"""Valve platform for the JUDO i-soft plus integration (waterstop)."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

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

_LOGGER = logging.getLogger(__name__)

# Write commands must not run in parallel against the slow embedded
# controller.
PARALLEL_UPDATES = 1

# Tolerant mapping of the device's status strings.
_CLOSED_STATES = frozenset({"close", "closed"})
_OPEN_STATES = frozenset({"open", "opened"})
_CLOSING_STATES = frozenset({"closing"})
_OPENING_STATES = frozenset({"opening"})

# After a command the motorized valve needs time to travel and the
# controller updates its status value lazily. Verify by re-reading only
# the valve status (single cheap request) until the target state shows
# up, instead of waiting for the next full scan interval.
_VERIFY_INTERVAL = 10  # seconds between status reads
_VERIFY_ATTEMPTS = 9  # ~90 s total


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
        self._entry = entry
        # "open"/"close" while a command is being verified, else None.
        self._pending_target: str | None = None
        self._verify_task: asyncio.Task | None = None

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
        return self._pending_target == "close" or self._raw_state() in _CLOSING_STATES

    @property
    def is_opening(self) -> bool:
        """Return True while the valve is opening."""
        return self._pending_target == "open" or self._raw_state() in _OPENING_STATES

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

        # Device acknowledged with status ok: show the transition right
        # away (opening/closing) and verify in the background.
        self._cancel_verify()
        self._pending_target = parameter
        self.async_write_ha_state()
        self._verify_task = self._entry.async_create_background_task(
            self.hass,
            self._async_verify(parameter),
            name=f"{DOMAIN} verify valve {parameter}",
        )

    async def _async_verify(self, target: str) -> None:
        """Re-read only the valve status until the target state shows up."""
        expected = _CLOSED_STATES if target == "close" else _OPEN_STATES
        try:
            for _ in range(_VERIFY_ATTEMPTS):
                await asyncio.sleep(_VERIFY_INTERVAL)
                try:
                    value = await self.hass.async_add_executor_job(
                        self.coordinator.api.read_value, "waterstop", "valve"
                    )
                except (OSError, JudoError, ValueError) as err:
                    _LOGGER.debug("Valve verify read failed: %s", err)
                    continue

                # Push into the coordinator data so the status sensor and
                # this entity stay consistent (notifies all listeners).
                data = dict(self.coordinator.data or {})
                data[KEY_WS_VALVE] = value
                self.coordinator.async_set_updated_data(data)

                if isinstance(value, str) and value.strip().lower() in expected:
                    _LOGGER.debug("Valve reached target state '%s'", target)
                    return
            _LOGGER.warning(
                "Valve did not report target state '%s' within %s s",
                target,
                _VERIFY_INTERVAL * _VERIFY_ATTEMPTS,
            )
        finally:
            self._pending_target = None
            self.async_write_ha_state()

    def _cancel_verify(self) -> None:
        if self._verify_task is not None and not self._verify_task.done():
            self._verify_task.cancel()
        self._verify_task = None
        self._pending_target = None

    async def async_will_remove_from_hass(self) -> None:
        """Cancel a running verification when the entity is removed."""
        self._cancel_verify()
        await super().async_will_remove_from_hass()
