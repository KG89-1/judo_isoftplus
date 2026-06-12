"""The JUDO i-soft plus integration."""
from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import JudoAuthError, JudoError, JudoISoftPlusAPI
from .const import CONF_SERIAL, DOMAIN, PLATFORMS
from .coordinator import JudoConfigEntry, JudoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: JudoConfigEntry) -> bool:
    """Set up JUDO i-soft plus from a config entry."""
    api = JudoISoftPlusAPI(
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_SERIAL],
    )

    try:
        await hass.async_add_executor_job(api.login)
        await hass.async_add_executor_job(api.connect)
    except JudoAuthError as err:
        # No reauth flow (yet) - retry instead of dead-ending the entry.
        raise ConfigEntryNotReady(f"Authentication failed: {err}") from err
    except (OSError, JudoError, ValueError) as err:
        raise ConfigEntryNotReady(f"Initial connection failed: {err}") from err

    coordinator = JudoCoordinator(hass, entry, api)
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The i-soft controller answers very slowly. Login/connect above already
    # validated the device (fail fast -> ConfigEntryNotReady), so the first
    # full data poll runs in the background instead of blocking HA startup.
    # Sensors show up immediately and fill in once the data arrives.
    entry.async_create_background_task(
        hass,
        coordinator.async_refresh(),
        name=f"{DOMAIN} initial refresh",
    )
    return True


async def _async_update_listener(hass: HomeAssistant, entry: JudoConfigEntry) -> None:
    """Reload the integration when options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: JudoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
