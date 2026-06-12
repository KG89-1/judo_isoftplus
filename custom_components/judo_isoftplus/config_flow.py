"""Config flow for the JUDO i-soft plus integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback

from .api import JudoAuthError, JudoError, JudoISoftPlusAPI
from .const import (
    CONF_SERIAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SERIAL): str,
    }
)


class JudoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of a JUDO i-soft plus device."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            user_input[CONF_SERIAL] = user_input[CONF_SERIAL].strip()

            # One config entry per device; if it already exists, update
            # the host (e.g. after an IP change) instead of duplicating.
            await self.async_set_unique_id(user_input[CONF_SERIAL])
            self._abort_if_unique_id_configured(
                updates={CONF_HOST: user_input[CONF_HOST]}
            )

            api = JudoISoftPlusAPI(
                user_input[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_SERIAL],
            )

            try:
                await self.hass.async_add_executor_job(api.login)
                await self.hass.async_add_executor_job(api.connect)
            except JudoAuthError:
                errors["base"] = "invalid_auth"
            except (OSError, JudoError, ValueError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface anything unexpected
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"JUDO i-soft plus ({user_input[CONF_SERIAL]})",
                    data=user_input,
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> JudoOptionsFlowHandler:
        """Return the options flow handler."""
        return JudoOptionsFlowHandler()


class JudoOptionsFlowHandler(OptionsFlow):
    """Handle the options (scan interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
