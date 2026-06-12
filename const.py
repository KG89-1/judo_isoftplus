"""Constants for the JUDO i-soft plus integration."""
from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "judo_isoftplus"

CONF_SERIAL: Final = "serial"

PLATFORMS: Final = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL: Final = 300  # seconds
MIN_SCAN_INTERVAL: Final = 60
MAX_SCAN_INTERVAL: Final = 3600

# Device info (sw/hw version) is only refreshed once per day.
DEVICE_INFO_MAX_AGE: Final = 24 * 3600  # seconds

# A drop of more than this many litres in "water total" is treated as a
# genuine counter reset instead of an hourly-rollover artefact.
LIVE_TOTAL_RESET_THRESHOLD: Final = 50  # litres

# Coordinator data keys: (api_group, api_command)
KEY_WATER_TOTAL: Final = ("consumption", "water%20total")
KEY_WATER_CURRENT: Final = ("consumption", "water%20current")
KEY_WATER_TOTAL_LIVE: Final = ("internal", "water_total_live")
KEY_SW_VERSION: Final = ("version", "software%20version")
KEY_HW_VERSION: Final = ("version", "hardware%20version")

DEVICE_INFO_KEYS: Final = (KEY_SW_VERSION, KEY_HW_VERSION)
