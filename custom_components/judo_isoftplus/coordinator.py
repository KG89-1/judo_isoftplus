"""DataUpdateCoordinator for the JUDO i-soft plus integration."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import JudoAuthError, JudoError, JudoISoftPlusAPI
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DEVICE_INFO_KEYS,
    DEVICE_INFO_MAX_AGE,
    DOMAIN,
    KEY_HW_VERSION,
    KEY_SW_VERSION,
    KEY_WATER_CURRENT,
    KEY_WATER_TOTAL,
    KEY_WATER_TOTAL_LIVE,
    KEY_WS_VALVE,
    LIVE_TOTAL_RESET_THRESHOLD,
)
from .sensor import SENSOR_DESCRIPTIONS, JudoSensorEntityDescription

_LOGGER = logging.getLogger(__name__)

type DataKey = tuple[str, str]
type JudoConfigEntry = ConfigEntry[JudoCoordinator]

# Entities outside the sensor platform: unique_id suffix -> required data
# pairs. These are enabled by default, so they are also part of the
# first-setup fallback below.
EXTRA_ENTITY_PAIRS: dict[str, set[DataKey]] = {
    "waterstop_valve": {KEY_WS_VALVE},
}


class JudoCoordinator(DataUpdateCoordinator[dict[DataKey, Any]]):
    """Polls only the values that belong to enabled entities."""

    config_entry: JudoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: JudoConfigEntry, api: JudoISoftPlusAPI
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.api = api

        # sw/hw version, refreshed at most once per DEVICE_INFO_MAX_AGE.
        self._device_info_cache: dict[DataKey, Any] = {}
        self._device_info_time: float | None = None

        # State for the synthetic "water_total_live" sensor.
        self._last_total: int | None = None
        self._last_combined: int | None = None

    # ------------------------------------------------------------------
    # Update cycle
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[DataKey, Any]:
        values: dict[DataKey, Any] = {}

        await self._async_refresh_device_info()
        values.update(self._device_info_cache)

        pairs = self._required_pairs()
        errors: list[str] = []

        # The device is an embedded controller - read sequentially on purpose.
        for group, command in pairs:
            try:
                values[(group, command)] = await self.hass.async_add_executor_job(
                    self.api.read_value, group, command
                )
            except JudoAuthError as err:
                # Abort immediately so we don't hammer the device with
                # one login attempt per remaining sensor.
                raise UpdateFailed(f"Authentication failed: {err}") from err
            except (OSError, JudoError, ValueError) as err:
                errors.append(f"{group}/{command}: {err}")

        if errors:
            if len(errors) == len(pairs):
                raise UpdateFailed("; ".join(errors))
            # Partial failure: affected sensors become unavailable via
            # their `available` property, everything else keeps working.
            _LOGGER.warning("Some values could not be read: %s", "; ".join(errors))

        self._compute_live_total(values)
        return values

    # ------------------------------------------------------------------
    # Device info cache (sw/hw version)
    # ------------------------------------------------------------------

    async def _async_refresh_device_info(self) -> None:
        now = time.monotonic()
        if (
            self._device_info_time is not None
            and now - self._device_info_time < DEVICE_INFO_MAX_AGE
        ):
            return

        cache: dict[DataKey, Any] = {}
        try:
            for group, command in DEVICE_INFO_KEYS:
                cache[(group, command)] = await self.hass.async_add_executor_job(
                    self.api.read_value, group, command
                )
        except (OSError, JudoError, ValueError) as err:
            if not self._device_info_cache:
                # Nothing cached yet (first refresh) -> real failure so
                # config entry setup retries properly.
                raise UpdateFailed(f"Could not read device info: {err}") from err
            _LOGGER.warning(
                "Device info refresh failed (%s), keeping cached values", err
            )
            return

        self._device_info_cache = cache
        self._device_info_time = now
        self._async_update_device_registry()

    def _async_update_device_registry(self) -> None:
        """Push sw/hw version into the device registry once known.

        The first full poll runs in the background after setup, so the
        device is registered before the versions are available - update
        them here instead of at entity creation time.
        """
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, self.config_entry.entry_id)}
        )
        if device is None:
            return
        sw = self._device_info_cache.get(KEY_SW_VERSION)
        hw = self._device_info_cache.get(KEY_HW_VERSION)
        device_registry.async_update_device(
            device.id,
            sw_version=str(sw) if sw is not None else None,
            hw_version=str(hw) if hw is not None else None,
        )

    # ------------------------------------------------------------------
    # Which values do we actually need to poll?
    # ------------------------------------------------------------------

    def _required_pairs(self) -> set[DataKey]:
        registry = er.async_get(self.hass)
        prefix = f"judo_{self.config_entry.entry_id}_"
        descriptions = {desc.key: desc for desc in SENSOR_DESCRIPTIONS}

        pairs: set[DataKey] = set()
        have_registry_entries = False

        for reg_entry in er.async_entries_for_config_entry(
            registry, self.config_entry.entry_id
        ):
            if not reg_entry.unique_id.startswith(prefix):
                continue
            have_registry_entries = True
            if reg_entry.disabled:
                continue
            suffix = reg_entry.unique_id[len(prefix) :]
            desc = descriptions.get(suffix)
            if desc is not None:
                pairs.update(self._pairs_for(desc))
            elif suffix in EXTRA_ENTITY_PAIRS:
                pairs.update(EXTRA_ENTITY_PAIRS[suffix])

        if not have_registry_entries:
            # Very first setup: entities are not registered yet, so poll
            # the values for all entities that are enabled by default.
            for desc in SENSOR_DESCRIPTIONS:
                if desc.entity_registry_enabled_default:
                    pairs.update(self._pairs_for(desc))
            for extra_pairs in EXTRA_ENTITY_PAIRS.values():
                pairs.update(extra_pairs)

        return pairs

    @staticmethod
    def _pairs_for(desc: JudoSensorEntityDescription) -> set[DataKey]:
        if desc.api_group == "internal":
            # The live total is computed from these two raw values.
            return {KEY_WATER_TOTAL, KEY_WATER_CURRENT}
        return {(desc.api_group, desc.api_command)}

    # ------------------------------------------------------------------
    # Synthetic live total
    # ------------------------------------------------------------------

    def _compute_live_total(self, values: dict[DataKey, Any]) -> None:
        """Combine 'water total' (hourly) and 'water current' (intra-hour).

        The device only folds the current hour into "water total" once per
        hour. During that rollover "current" resets before (or while)
        "total" is increased, which would otherwise make the combined
        value dip - and a dip on a total_increasing sensor corrupts the
        long-term statistics. A simple monotonic guard covers all
        rollover variants; only a large drop (> LIVE_TOTAL_RESET_THRESHOLD)
        is accepted as a genuine counter reset.
        """
        raw_total = values.get(KEY_WATER_TOTAL)
        raw_current = values.get(KEY_WATER_CURRENT)

        if not isinstance(raw_total, int) or not isinstance(raw_current, int):
            # Raw values missing/unparsable -> leave key absent, the live
            # sensor reports unavailable for this cycle.
            return

        candidate = raw_total + raw_current

        if self._last_combined is None or self._last_total is None:
            combined = candidate
        elif raw_total < self._last_total - LIVE_TOTAL_RESET_THRESHOLD:
            _LOGGER.info(
                "Water total counter reset detected (%s -> %s L)",
                self._last_total,
                raw_total,
            )
            combined = candidate
        else:
            combined = max(candidate, self._last_combined)

        self._last_total = raw_total
        self._last_combined = combined
        values[KEY_WATER_TOTAL_LIVE] = combined / 1000.0  # litres -> m³
