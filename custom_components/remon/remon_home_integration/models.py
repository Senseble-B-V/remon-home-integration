"""Data models for the Remon LAN status contract.

The firmware serves one JSON object on ``GET /api/status`` and advertises the same identity in the
TXT records of its ``_saltlevel._tcp`` mDNS service::

    {"id": "SaltBuddy-a1b2c3d4e5f6", "type": "SaltBuddy", "fw": "382de8e",
     "salt_level": 64, "sensor_error": false, "leak": false}

Parsing is strict about the fields the contract defines (a wrong type is a broken device, not
something to guess around) and ignores fields it does not know, so newer firmware that adds
fields without bumping ``api`` keeps working.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeGuard

from .exceptions import RemonDiscoveryError, RemonResponseError, RemonUnsupportedApiError

#: Highest ``api`` contract version this library understands. Firmware that does not send
#: ``api`` yet speaks version 1.
SUPPORTED_API_VERSION = 1

#: mDNS service type the firmware advertises, in the form Home Assistant's zeroconf uses.
ZEROCONF_SERVICE_TYPE = "_saltlevel._tcp.local."

DEVICE_TYPE_SALTBUDDY = "SaltBuddy"
DEVICE_TYPE_SOFTENER = "Softener"
DEVICE_TYPE_SOFTENER_DF = "SoftenerDF"

MANUFACTURER = "Remon"

# Must match FAMILY_DISPLAY_NAME in the firmware's config.h and DeviceTypeHelper.DisplayName in
# the backend. The device type is an internal marker ("DF" in particular) and is never shown.
_FAMILY_DISPLAY_NAMES: dict[str, str] = {
    DEVICE_TYPE_SALTBUDDY: "SaltBuddy",
    DEVICE_TYPE_SOFTENER: "Remon Waterontharder",
    DEVICE_TYPE_SOFTENER_DF: "Remon Waterontharder",
}
_UNKNOWN_FAMILY_DISPLAY_NAME = "Remon device"

# "<FIRMWARE_TYPE>-<DeviceId>": the ID is a hostname label, so only letters, digits and dashes.
_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,63}$")
# DeviceId is the base MAC as 12 lower-case hex digits, after the last dash.
_MAC_SUFFIX_RE = re.compile(r"-([0-9a-fA-F]{12})$")
_DEVICE_TYPES_BY_LOWER_NAME: dict[str, str] = {
    device_type.lower(): device_type
    for device_type in (DEVICE_TYPE_SALTBUDDY, DEVICE_TYPE_SOFTENER, DEVICE_TYPE_SOFTENER_DF)
}


def family_display_name(device_type: str | None) -> str:
    """Return the user-facing family name for a firmware ``type``.

    ``SaltBuddy`` gives "SaltBuddy", ``Softener`` and ``SoftenerDF`` give "Remon Waterontharder",
    anything else (including ``None``) gives "Remon device".
    """
    if device_type is None:
        return _UNKNOWN_FAMILY_DISPLAY_NAME
    return _FAMILY_DISPLAY_NAMES.get(device_type, _UNKNOWN_FAMILY_DISPLAY_NAME)


def mac_from_device_id(device_id: str) -> str | None:
    """Return the MAC address embedded in a device ID as ``aa:bb:cc:dd:ee:ff``.

    Returns ``None`` when the ID does not end in ``-`` plus 12 hex digits.
    """
    match = _MAC_SUFFIX_RE.search(device_id)
    if match is None:
        return None
    digits = match.group(1).lower()
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def device_id_from_hostname(hostname: str) -> str | None:
    """Return the device ID of a Remon device from its DHCP host name, in any letter case.

    The firmware uses its device ID as DHCP host name, but Home Assistant's DHCP discovery
    lower-cases host names (``softenerdf-0123456789ab``) while the device ID keeps the type's
    capitals (``SoftenerDF-0123456789ab``). Only the known firmware types followed by a 12-digit
    hex DeviceId are recognised; anything else gives ``None``.
    """
    label = hostname.split(".", 1)[0]
    match = _MAC_SUFFIX_RE.search(label)
    if match is None:
        return None
    device_type = _DEVICE_TYPES_BY_LOWER_NAME.get(label[: match.start()].lower())
    if device_type is None:
        return None
    return f"{device_type}-{match.group(1).lower()}"


def is_valid_device_id(device_id: object) -> TypeGuard[str]:
    """Return whether ``device_id`` is usable as a device ID (hostname-safe, non-empty)."""
    return isinstance(device_id, str) and _DEVICE_ID_RE.fullmatch(device_id) is not None


@dataclass(frozen=True, slots=True, kw_only=True)
class RemonStatus:
    """One reading from ``GET /api/status``."""

    #: ``<FIRMWARE_TYPE>-<DeviceId>``, stable across firmware variants; use as unique ID.
    id: str
    #: Internal firmware type (``SaltBuddy``, ``Softener``, ``SoftenerDF``). Never show it to a
    #: user; use :attr:`display_name`.
    type: str
    #: Firmware version: the short git commit hash, an opaque string (not semver).
    fw: str
    #: Salt level in percent, 0..100, or ``None`` while the sensor has no sample yet.
    salt_level: int | None
    #: The salt distance sensor reports a fault (also true while it has no sample yet).
    sensor_error: bool
    #: A water leak is detected (debounced in firmware, about 11 s).
    leak: bool
    #: Contract version, or ``None`` for firmware that does not report it yet (version 1).
    api: int | None = None

    @property
    def display_name(self) -> str:
        """User-facing family name, see :func:`family_display_name`."""
        return family_display_name(self.type)

    @property
    def mac(self) -> str | None:
        """MAC address derived from :attr:`id`, or ``None`` if it carries none."""
        return mac_from_device_id(self.id)

    @classmethod
    def from_dict(cls, data: object) -> RemonStatus:
        """Validate a decoded JSON body and build a :class:`RemonStatus`.

        Raises:
            RemonUnsupportedApiError: ``api`` is newer than :data:`SUPPORTED_API_VERSION`.
            RemonResponseError: ``data`` is not an object, or a field is missing or mistyped.

        """
        if not isinstance(data, Mapping):
            raise RemonResponseError(f"Expected a JSON object, got {type(data).__name__}")

        api = _optional_api(data)

        device_id = _required(data, "id", str)
        if not is_valid_device_id(device_id):
            raise RemonResponseError(f"Invalid device id {device_id!r}")

        return cls(
            id=device_id,
            type=_required(data, "type", str),
            fw=_required(data, "fw", str),
            salt_level=_salt_level(data),
            sensor_error=_required(data, "sensor_error", bool),
            leak=_required(data, "leak", bool),
            api=api,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RemonDiscovery:
    """Identity advertised in the TXT records of the ``_saltlevel._tcp`` mDNS service."""

    id: str
    #: Internal firmware type, empty if the record had none. Show :attr:`display_name` instead.
    type: str
    fw: str
    api: int | None = None

    @property
    def display_name(self) -> str:
        """User-facing family name, see :func:`family_display_name`."""
        return family_display_name(self.type or None)

    @property
    def mac(self) -> str | None:
        """MAC address derived from :attr:`id`, or ``None`` if it carries none."""
        return mac_from_device_id(self.id)

    @classmethod
    def from_txt(
        cls, properties: Mapping[str, str | None] | Mapping[bytes, bytes | None]
    ) -> RemonDiscovery:
        """Parse mDNS TXT records.

        Accepts both Home Assistant's decoded ``ZeroconfServiceInfo.properties``
        (``dict[str, str]``) and python-zeroconf's raw ``dict[bytes, bytes | None]``. Keys are
        matched case-insensitively, as DNS-SD requires. Only ``id`` is mandatory; ``type`` and
        ``fw`` default to empty strings and the authoritative values come from the first status
        poll anyway.

        Raises:
            RemonDiscoveryError: ``id`` is missing or not a valid device ID, or ``api`` is
                present but not a positive integer.

        """
        txt: dict[str, str] = {}
        for raw_key, raw_value in properties.items():
            try:
                key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                value = raw_value.decode() if isinstance(raw_value, bytes) else raw_value
            except UnicodeDecodeError:
                continue
            if value is not None:
                txt[key.lower()] = value

        device_id = txt.get("id")
        if not is_valid_device_id(device_id):
            raise RemonDiscoveryError(f"TXT record has no valid 'id': {device_id!r}")

        api: int | None = None
        if "api" in txt:
            raw_api = txt["api"]
            if not raw_api.isdecimal() or int(raw_api) < 1:
                raise RemonDiscoveryError(f"TXT record has an invalid 'api': {raw_api!r}")
            api = int(raw_api)

        return cls(id=device_id, type=txt.get("type", ""), fw=txt.get("fw", ""), api=api)

    @property
    def is_supported(self) -> bool:
        """Whether this library understands the advertised contract version."""
        return self.api is None or self.api <= SUPPORTED_API_VERSION


_MISSING: Any = object()


def _is_int(value: object) -> bool:
    # bool is a subclass of int; JSON true/false must not pass as a number.
    return isinstance(value, int) and not isinstance(value, bool)


def _required[T](data: Mapping[str, Any], key: str, kind: type[T]) -> T:
    value = data.get(key, _MISSING)
    if value is _MISSING:
        raise RemonResponseError(f"Missing field {key!r}")
    if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
        raise RemonResponseError(
            f"Field {key!r} must be {kind.__name__}, got {type(value).__name__}"
        )
    return value


def _salt_level(data: Mapping[str, Any]) -> int | None:
    value = data.get("salt_level", _MISSING)
    if value is _MISSING:
        raise RemonResponseError("Missing field 'salt_level'")
    if value is None:
        return None
    if not _is_int(value) or not 0 <= value <= 100:
        raise RemonResponseError(
            f"Field 'salt_level' must be an integer 0..100 or null, got {value!r}"
        )
    return int(value)


def _optional_api(data: Mapping[str, Any]) -> int | None:
    api = data.get("api")
    if api is None:
        return None
    if not _is_int(api) or api < 1:
        raise RemonResponseError(f"Field 'api' must be a positive integer, got {api!r}")
    if api > SUPPORTED_API_VERSION:
        raise RemonUnsupportedApiError(api, SUPPORTED_API_VERSION)
    return int(api)
