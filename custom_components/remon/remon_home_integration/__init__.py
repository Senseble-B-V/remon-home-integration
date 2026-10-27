"""Async client for the local HTTP API of Remon salt level monitors.

Bundled inside the Remon Home Assistant integration (HACS copies only custom_components/remon),
so it must not import homeassistant and must keep working standalone: the tests and
``python -m remon_home_integration`` use it without Home Assistant.
"""

from .client import DEFAULT_PORT, DEFAULT_TIMEOUT, STATUS_PATH, RemonClient
from .exceptions import (
    RemonConnectionError,
    RemonDiscoveryError,
    RemonError,
    RemonResponseError,
    RemonUnsupportedApiError,
)
from .models import (
    DEVICE_TYPE_SALTBUDDY,
    DEVICE_TYPE_SOFTENER,
    DEVICE_TYPE_SOFTENER_DF,
    MANUFACTURER,
    SUPPORTED_API_VERSION,
    ZEROCONF_SERVICE_TYPE,
    RemonDiscovery,
    RemonStatus,
    device_id_from_hostname,
    family_display_name,
    is_valid_device_id,
    mac_from_device_id,
)

__all__ = [
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "DEVICE_TYPE_SALTBUDDY",
    "DEVICE_TYPE_SOFTENER",
    "DEVICE_TYPE_SOFTENER_DF",
    "MANUFACTURER",
    "STATUS_PATH",
    "SUPPORTED_API_VERSION",
    "ZEROCONF_SERVICE_TYPE",
    "RemonClient",
    "RemonConnectionError",
    "RemonDiscovery",
    "RemonDiscoveryError",
    "RemonError",
    "RemonResponseError",
    "RemonStatus",
    "RemonUnsupportedApiError",
    "device_id_from_hostname",
    "family_display_name",
    "is_valid_device_id",
    "mac_from_device_id",
]
