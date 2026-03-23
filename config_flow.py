import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL
from .const import DOMAIN, CONF_SERIAL, DEFAULT_SCAN_INTERVAL
from .api import JudoSoftplusAPI
import asyncio
import logging

_LOGGER = logging.getLogger(__name__)


class JudoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            _LOGGER.info(
                "Testing JUDO Softplus connection to host '%s'...",
                user_input[CONF_HOST]
            )

            api = JudoSoftplusAPI(
                user_input[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_SERIAL]
            )

            try:
                await asyncio.to_thread(api.login)
                await asyncio.to_thread(api.connect)
                _LOGGER.info("Connection test successful")

            except Exception as e:
                _LOGGER.error("Connection test failed: %s", e)
                errors["base"] = "cannot_connect"

            else:
                return self.async_create_entry(
                    title="JUDO i-soft Plus",
                    data=user_input,
                    options={"scan_interval": DEFAULT_SCAN_INTERVAL},
                )

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_SERIAL): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return JudoOptionsFlowHandler(config_entry)


class JudoOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            _LOGGER.info("Options updated: scan_interval=%s", user_input.get(CONF_SCAN_INTERVAL))
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema({
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ): vol.All(int, vol.Range(min=60, max=3600)),
        })

        return self.async_show_form(step_id="init", data_schema=schema)
