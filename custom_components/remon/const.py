"""Constants for the Remon integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Final

DOMAIN: Final = "remon"

LOGGER = logging.getLogger(__package__)

# The device samples the leak flag every second (debounced for about 11 s) and the salt level
# every 30 s. Polling once a minute means a leak shows up to a minute after the device detects it.
SCAN_INTERVAL: Final = timedelta(seconds=60)
