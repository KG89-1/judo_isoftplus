from homeassistant.core import HomeAssistant
from datetime import datetime, timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

from .const import DOMAIN, CONF_SERIAL, DEFAULT_SCAN_INTERVAL
from .api import JudoSoftplusAPI
from .sensor import SENSOR_TYPES, HIDDEN_SENSOR_TYPES

import logging
import asyncio

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    api = JudoSoftplusAPI(
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_SERIAL]
    )

    try:
        await asyncio.to_thread(api.login)
        await asyncio.to_thread(api.connect)
    except Exception as err:
        raise ConfigEntryNotReady(f"Initial connection failed: {err}") from err

    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)

    sensor_map = {
        sensor_id: (group, command)
        for sensor_id, (_, _, group, command, _) in SENSOR_TYPES.items()
    }

    hidden_map = {
        key: (group, command)
        for key, (group, command) in HIDDEN_SENSOR_TYPES.items()
    }

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": None,
        "sensor_map": sensor_map,
        "hidden_map": hidden_map,
        "hidden_cache": {},
        "hidden_cache_time": None,

        # Live total tracking
        "live_total": {
            "last_total": None,
            "last_current": None,
            "last_combined": None,
        },
    }

    async def async_update_data():
        data_container = hass.data[DOMAIN][entry.entry_id]
        hidden_cache = data_container["hidden_cache"]
        hidden_cache_time = data_container["hidden_cache_time"]

        now = datetime.now()
        max_age = timedelta(hours=24)

        values = {}

        # Hidden cache refresh
        if hidden_cache_time is None or now - hidden_cache_time > max_age:
            new_cache = {}
            for group, command in hidden_map.values():
                try:
                    val = await asyncio.to_thread(api.read_value, group, command)
                    new_cache[(group, command)] = val
                except Exception as err:
                    raise UpdateFailed(f"Failed to fetch {group}/{command}: {err}")
            data_container["hidden_cache"] = new_cache
            data_container["hidden_cache_time"] = now
            hidden_cache = new_cache

        values.update(hidden_cache)

        # ------------------------------------------------------------
        # Determine if live-total sensor is active
        # ------------------------------------------------------------
        entity_reg = er.async_get(hass)
        prefix = f"judo_{entry.entry_id}_"

        live_sensor_active = False

        for ent in entity_reg.entities.values():
            if (
                ent.unique_id == f"judo_{entry.entry_id}_water_total_live"
                and ent.disabled is False
            ):
                live_sensor_active = True
                break

        # ------------------------------------------------------------
        # Determine required value fetches
        # ------------------------------------------------------------
        forced_pairs = set()

        if live_sensor_active:
            forced_pairs.add(("consumption", "water%20total"))
            forced_pairs.add(("consumption", "water%20current"))

        for ent in entity_reg.entities.values():
            if ent.disabled or not ent.unique_id.startswith(prefix):
                continue

            sensor_id = ent.unique_id[len(prefix):]

            if sensor_id in sensor_map:
                group, command = sensor_map[sensor_id]

                if group == "internal":
                    continue

                forced_pairs.add((group, command))

        # ------------------------------------------------------------
        # Read all required sensors ONCE
        # ------------------------------------------------------------
        for group, command in forced_pairs:
            try:
                val = await asyncio.to_thread(api.read_value, group, command)
                values[(group, command)] = val
            except Exception as err:
                raise UpdateFailed(f"Failed to fetch {group}/{command}: {err}")

        # ------------------------------------------------------------
        # Live-total calculation
        # ------------------------------------------------------------
        state = data_container["live_total"]

        raw_total = values.get(("consumption", "water%20total"))
        raw_current = values.get(("consumption", "water%20current"))

        # No valid data yet → unavailable
        if raw_total is None or raw_current is None:
            values[("internal", "water_total_live")] = None
            return values

        # First-time initialization
        if state["last_total"] is None or state["last_current"] is None:
            combined = raw_total + raw_current
            state["last_total"] = raw_total
            state["last_current"] = raw_current
            state["last_combined"] = combined
            values[("internal", "water_total_live")] = combined / 1000.0
            return values

        # Detect reset (large drop)
        if raw_total < state["last_total"]:
            if state["last_total"] - raw_total > 50:
                combined = raw_total  # real reset
            else:
                combined = state["last_combined"]
        # Detect hour rollover
        elif raw_total == state["last_total"] and raw_current < state["last_current"]:
            combined = state["last_combined"]
        else:
            combined = raw_total + raw_current

        # Update state values
        state["last_total"] = raw_total
        state["last_current"] = raw_current
        state["last_combined"] = combined

        values[("internal", "water_total_live")] = combined / 1000.0

        return values

    # ------------------------------------------------------------
    # Coordinator setup
    # ------------------------------------------------------------
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="judo_coordinator",
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )

    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload
