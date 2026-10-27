"""Tests for the config flow: manual host, zeroconf, DHCP and reconfigure."""

from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import ClientError
from homeassistant.config_entries import (
    SOURCE_DHCP,
    SOURCE_USER,
    SOURCE_ZEROCONF,
    ConfigEntryState,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.remon.const import DOMAIN

from .conftest import DEVICE_ID, HOST, STATUS_URL, mock_status, setup_entry

NEW_HOST = "192.168.1.77"


def zeroconf_info(
    properties: dict[str, Any] | None = None, host: str = HOST
) -> ZeroconfServiceInfo:
    """Service info as Home Assistant passes it for a ``_saltlevel._tcp`` announcement."""
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        port=80,
        hostname=f"{DEVICE_ID}.local.",
        type="_saltlevel._tcp.local.",
        name=f"{DEVICE_ID}._saltlevel._tcp.local.",
        properties=(
            properties
            if properties is not None
            else {"id": DEVICE_ID, "type": "SaltBuddy", "fw": "382de8e"}
        ),
    )


def dhcp_info(
    hostname: str = DEVICE_ID.lower(), ip: str = HOST, mac: str = "a1b2c3d4e5f6"
) -> DhcpServiceInfo:
    """Service info as Home Assistant's DHCP watcher passes it (host name lower-cased)."""
    return DhcpServiceInfo(ip=ip, hostname=hostname, macaddress=mac)


# --- user ------------------------------------------------------------------------------------


async def test_user(hass: HomeAssistant, device: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: f"  {HOST} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SaltBuddy"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == DEVICE_ID


@pytest.mark.parametrize(
    ("mock_kwargs", "host", "errors"),
    [
        ({"exc": ClientError()}, HOST, {"base": "cannot_connect"}),
        ({"exc": TimeoutError()}, HOST, {"base": "cannot_connect"}),
        ({"text": "<html>router</html>"}, HOST, {"base": "not_remon_device"}),
        (
            {"json": {"id": DEVICE_ID, "type": "SaltBuddy", "api": 99}},
            HOST,
            {"base": "unsupported_api"},
        ),
        ({"text": "{}"}, f"http://{HOST}", {CONF_HOST: "invalid_host"}),
    ],
)
async def test_user_errors_then_recover(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_kwargs: dict[str, Any],
    host: str,
    errors: dict[str, str],
) -> None:
    aioclient_mock.get(STATUS_URL, **mock_kwargs)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: host})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors

    mock_status(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_unexpected_error(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(
        "custom_components.remon.config_flow.RemonClient.get_status", side_effect=RuntimeError
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_already_configured_updates_host(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_status(aioclient_mock, host=NEW_HOST)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: NEW_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == NEW_HOST


# --- zeroconf --------------------------------------------------------------------------------


async def test_zeroconf(hass: HomeAssistant, device: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"name": "SaltBuddy", "host": HOST}
    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["title_placeholders"] == {"name": "SaltBuddy", "host": HOST}
    assert device.call_count == 0

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SaltBuddy"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == DEVICE_ID


async def test_zeroconf_updates_host_of_configured_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info(host=NEW_HOST)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == NEW_HOST
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(
    ("info", "reason"),
    [
        (zeroconf_info(properties={"type": "SaltBuddy"}), "not_remon_device"),
        (zeroconf_info(properties={"id": "not a device id"}), "not_remon_device"),
        (zeroconf_info(host="fe80::1"), "ipv6_not_supported"),
        (zeroconf_info(properties={"id": DEVICE_ID, "api": "2"}), "unsupported_api"),
    ],
)
async def test_zeroconf_abort(hass: HomeAssistant, info: ZeroconfServiceInfo, reason: str) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


async def test_discovery_confirm_cannot_connect_then_recover(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(STATUS_URL, exc=ClientError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["errors"] == {"base": "cannot_connect"}

    mock_status(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_discovery_confirm_wrong_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # The address was handed to another device between discovery and confirmation.
    mock_status(aioclient_mock, "softener_df_leak.json")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


# --- DHCP ------------------------------------------------------------------------------------


async def test_dhcp_new_device_restores_id_case(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_status(aioclient_mock, "softener_df_leak.json", host=NEW_HOST)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=dhcp_info("softenerdf-0123456789ab", NEW_HOST, "0123456789ab"),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {
        "name": "Remon Waterontharder",
        "host": NEW_HOST,
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Remon Waterontharder"
    assert result["data"] == {CONF_HOST: NEW_HOST}
    assert result["result"].unique_id == "SoftenerDF-0123456789ab"


async def test_dhcp_updates_host_without_reading_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    # The device sends its DHCP request before its HTTP server listens.
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=dhcp_info(ip=NEW_HOST)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == NEW_HOST
    assert aioclient_mock.call_count == 0


async def test_dhcp_registered_device_matched_on_mac(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    # The registered_devices matcher fires on the MAC, whatever host name the network reports.
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=dhcp_info(hostname="espressif", ip=NEW_HOST),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == NEW_HOST


@pytest.mark.parametrize("hostname", ["softener-kitchen", "espressif"])
async def test_dhcp_not_remon_device(hass: HomeAssistant, hostname: str) -> None:
    # Configured entries without a MAC in their ID, or with another MAC, do not match.
    MockConfigEntry(domain=DOMAIN, unique_id="Future", data={CONF_HOST: HOST}).add_to_hass(hass)
    MockConfigEntry(
        domain=DOMAIN, unique_id="SaltBuddy-0000000000aa", data={CONF_HOST: HOST}
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=dhcp_info(hostname=hostname)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_remon_device"


async def test_dhcp_while_zeroconf_flow_in_progress(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=dhcp_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


# --- reconfigure -----------------------------------------------------------------------------


async def test_reconfigure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    mock_status(aioclient_mock)
    await setup_entry(hass, mock_config_entry)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    aioclient_mock.get(f"http://{NEW_HOST}/api/status", exc=ClientError())
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: NEW_HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_status(aioclient_mock, host=NEW_HOST)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: NEW_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_HOST] == NEW_HOST
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_status(aioclient_mock, "softener_df_leak.json", host=NEW_HOST)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: NEW_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert mock_config_entry.data[CONF_HOST] == HOST
