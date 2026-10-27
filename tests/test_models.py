"""Tests for the status and discovery models."""

from __future__ import annotations

import json
from typing import Any

import pytest

from remon_home_integration import (
    SUPPORTED_API_VERSION,
    RemonDiscovery,
    RemonDiscoveryError,
    RemonResponseError,
    RemonStatus,
    RemonUnsupportedApiError,
    device_id_from_hostname,
    family_display_name,
    is_valid_device_id,
    mac_from_device_id,
)

from .conftest import load_fixture

VALID: dict[str, Any] = {
    "id": "SaltBuddy-a1b2c3d4e5f6",
    "type": "SaltBuddy",
    "fw": "382de8e",
    "salt_level": 64,
    "sensor_error": False,
    "leak": False,
}


def with_(**changes: Any) -> dict[str, Any]:
    return {**VALID, **changes}


def without(key: str) -> dict[str, Any]:
    return {k: v for k, v in VALID.items() if k != key}


# --- recorded responses ---------------------------------------------------------------------


def test_saltbuddy() -> None:
    status = RemonStatus.from_dict(json.loads(load_fixture("saltbuddy.json")))
    assert status == RemonStatus(
        id="SaltBuddy-a1b2c3d4e5f6",
        type="SaltBuddy",
        fw="382de8e",
        salt_level=64,
        sensor_error=False,
        leak=False,
        api=None,
    )
    assert status.display_name == "SaltBuddy"
    assert status.mac == "a1:b2:c3:d4:e5:f6"


def test_softener_df_leak_never_shows_df() -> None:
    status = RemonStatus.from_dict(json.loads(load_fixture("softener_df_leak.json")))
    assert status.leak is True
    assert status.salt_level == 0
    assert status.fw == "40e82dc-dirty"
    assert status.display_name == "Remon Waterontharder"
    assert "DF" not in status.display_name


def test_no_salt_sample_yet() -> None:
    status = RemonStatus.from_dict(json.loads(load_fixture("softener_no_sample.json")))
    assert status.salt_level is None
    assert status.sensor_error is True
    assert status.display_name == "Remon Waterontharder"


def test_unknown_type_with_api_and_extra_field() -> None:
    status = RemonStatus.from_dict(json.loads(load_fixture("unknown_type_api1.json")))
    assert status.type == "Future"
    assert status.display_name == "Remon device"
    assert status.salt_level == 100
    assert status.api == 1


# --- display names and identity -------------------------------------------------------------


@pytest.mark.parametrize(
    ("device_type", "expected"),
    [
        ("SaltBuddy", "SaltBuddy"),
        ("Softener", "Remon Waterontharder"),
        ("SoftenerDF", "Remon Waterontharder"),
        ("FLOW_TEST", "Remon device"),
        ("saltbuddy", "Remon device"),
        ("", "Remon device"),
        (None, "Remon device"),
    ],
)
def test_family_display_name(device_type: str | None, expected: str) -> None:
    assert family_display_name(device_type) == expected


@pytest.mark.parametrize(
    ("device_id", "expected"),
    [
        ("SaltBuddy-a1b2c3d4e5f6", "a1:b2:c3:d4:e5:f6"),
        ("SoftenerDF-A1B2C3D4E5F6", "a1:b2:c3:d4:e5:f6"),
        ("SaltBuddy-a1b2c3d4e5", None),
        ("SaltBuddy-a1b2c3d4e5f6a", None),
        ("a1b2c3d4e5f6", None),
        ("SaltBuddy-a1b2c3d4e5g6", None),
    ],
)
def test_mac_from_device_id(device_id: str, expected: str | None) -> None:
    assert mac_from_device_id(device_id) == expected


@pytest.mark.parametrize(
    ("hostname", "expected"),
    [
        # Home Assistant's DHCP discovery passes host names lower-cased.
        ("saltbuddy-a1b2c3d4e5f6", "SaltBuddy-a1b2c3d4e5f6"),
        ("softener-a1b2c3d4e5f6", "Softener-a1b2c3d4e5f6"),
        ("softenerdf-0123456789ab", "SoftenerDF-0123456789ab"),
        ("SoftenerDF-0123456789AB", "SoftenerDF-0123456789ab"),
        ("saltbuddy-a1b2c3d4e5f6.lan", "SaltBuddy-a1b2c3d4e5f6"),
        ("future-a1b2c3d4e5f6", None),
        ("saltbuddy-a1b2c3d4e5", None),
        ("saltbuddy-a1b2c3d4e5g6", None),
        ("saltbuddy", None),
        # The fallback host names of builds without the LAN integration.
        ("remon-waterontharder-df", None),
        ("", None),
    ],
)
def test_device_id_from_hostname(hostname: str, expected: str | None) -> None:
    assert device_id_from_hostname(hostname) == expected


@pytest.mark.parametrize(
    ("device_id", "expected"),
    [
        ("SaltBuddy-a1b2c3d4e5f6", True),
        ("x", True),
        ("a" * 63, True),
        ("a" * 64, False),
        ("", False),
        ("Salt Buddy", False),
        ("SaltBuddy_a1", False),
        ("SaltBuddy-a1\n", False),
        (None, False),
        (42, False),
    ],
)
def test_is_valid_device_id(device_id: object, expected: bool) -> None:
    assert is_valid_device_id(device_id) is expected


# --- strict validation ----------------------------------------------------------------------


@pytest.mark.parametrize("key", ["id", "type", "fw", "salt_level", "sensor_error", "leak"])
def test_missing_field(key: str) -> None:
    with pytest.raises(RemonResponseError, match=key):
        RemonStatus.from_dict(without(key))


@pytest.mark.parametrize(
    "data",
    [
        with_(id=""),
        with_(id="not a hostname"),
        with_(id=12),
        with_(id=None),
        with_(type=5),
        with_(type=None),
        with_(fw=None),
        with_(fw=382),
        with_(salt_level=True),
        with_(salt_level="64"),
        with_(salt_level=64.0),
        with_(salt_level=-1),
        with_(salt_level=101),
        with_(sensor_error=0),
        with_(sensor_error="false"),
        with_(sensor_error=None),
        with_(leak=1),
        with_(leak="true"),
        with_(api=0),
        with_(api="1"),
        with_(api=True),
        with_(api=1.0),
    ],
)
def test_invalid_field(data: dict[str, Any]) -> None:
    with pytest.raises(RemonResponseError):
        RemonStatus.from_dict(data)


@pytest.mark.parametrize("data", [[], "status", 42, None, True, [VALID]])
def test_not_an_object(data: object) -> None:
    with pytest.raises(RemonResponseError, match="JSON object"):
        RemonStatus.from_dict(data)


@pytest.mark.parametrize("salt_level", [0, 1, 50, 99, 100, None])
def test_salt_level_bounds(salt_level: int | None) -> None:
    assert RemonStatus.from_dict(with_(salt_level=salt_level)).salt_level == salt_level


def test_api_null_means_not_reported() -> None:
    assert RemonStatus.from_dict(with_(api=None)).api is None


def test_api_supported() -> None:
    assert RemonStatus.from_dict(with_(api=SUPPORTED_API_VERSION)).api == SUPPORTED_API_VERSION


def test_api_too_new() -> None:
    newer = SUPPORTED_API_VERSION + 1
    with pytest.raises(RemonUnsupportedApiError) as exc_info:
        # Even a payload that is otherwise garbage must report the version problem first.
        RemonStatus.from_dict({"api": newer, "salt_level": "lots"})
    assert exc_info.value.api == newer
    assert exc_info.value.supported == SUPPORTED_API_VERSION
    assert isinstance(exc_info.value, RemonResponseError)


def test_unknown_fields_ignored() -> None:
    status = RemonStatus.from_dict(with_(capacity=1200, nested={"a": [1, 2]}))
    assert status == RemonStatus.from_dict(VALID)


def test_status_is_immutable() -> None:
    status = RemonStatus.from_dict(VALID)
    with pytest.raises(AttributeError):
        status.leak = True  # type: ignore[misc]


# --- mDNS TXT records -----------------------------------------------------------------------


def test_discovery_from_home_assistant_properties() -> None:
    info = RemonDiscovery.from_txt(
        {"id": "SoftenerDF-a1b2c3d4e5f6", "type": "SoftenerDF", "fw": "382de8e"}
    )
    assert info == RemonDiscovery(id="SoftenerDF-a1b2c3d4e5f6", type="SoftenerDF", fw="382de8e")
    assert info.display_name == "Remon Waterontharder"
    assert info.mac == "a1:b2:c3:d4:e5:f6"
    assert info.api is None
    assert info.is_supported


def test_discovery_from_raw_zeroconf_records() -> None:
    info = RemonDiscovery.from_txt(
        {b"id": b"SaltBuddy-a1b2c3d4e5f6", b"type": b"SaltBuddy", b"fw": b"abc1234", b"api": b"1"}
    )
    assert info.id == "SaltBuddy-a1b2c3d4e5f6"
    assert info.display_name == "SaltBuddy"
    assert info.api == 1
    assert info.is_supported


def test_discovery_keys_case_insensitive() -> None:
    info = RemonDiscovery.from_txt({"ID": "SaltBuddy-a1b2c3d4e5f6", "Type": "SaltBuddy"})
    assert info.id == "SaltBuddy-a1b2c3d4e5f6"
    assert info.type == "SaltBuddy"


def test_discovery_only_id() -> None:
    info = RemonDiscovery.from_txt({"id": "SaltBuddy-a1b2c3d4e5f6"})
    assert info.type == ""
    assert info.fw == ""
    assert info.display_name == "Remon device"


def test_discovery_skips_undecodable_and_valueless_records() -> None:
    info = RemonDiscovery.from_txt(
        {b"id": b"SaltBuddy-a1b2c3d4e5f6", b"\xff": b"x", b"fw": b"\xfe", b"type": None}
    )
    assert info.fw == ""
    assert info.type == ""


@pytest.mark.parametrize(
    "properties",
    [
        {},
        {"type": "SaltBuddy"},
        {"id": ""},
        {"id": "not valid!"},
        {"id": None},
        {b"id": None},
        {b"id": b"\xff\xfe"},
    ],
)
def test_discovery_without_valid_id(properties: dict[Any, Any]) -> None:
    with pytest.raises(RemonDiscoveryError):
        RemonDiscovery.from_txt(properties)


@pytest.mark.parametrize("api", ["0", "-1", "one", "", "1.0", "²"])
def test_discovery_invalid_api(api: str) -> None:
    with pytest.raises(RemonDiscoveryError, match="api"):
        RemonDiscovery.from_txt({"id": "SaltBuddy-a1b2c3d4e5f6", "api": api})


def test_discovery_newer_api_is_parsed_but_unsupported() -> None:
    # Discovery must not fail on a newer device: the integration decides how to tell the user.
    info = RemonDiscovery.from_txt(
        {"id": "SaltBuddy-a1b2c3d4e5f6", "api": str(SUPPORTED_API_VERSION + 1)}
    )
    assert info.api == SUPPORTED_API_VERSION + 1
    assert not info.is_supported
