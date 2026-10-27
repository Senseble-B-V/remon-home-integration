"""Config flow for Remon: mDNS (zeroconf) and DHCP discovery, manual host, reconfigure.

The config entry's unique ID is the device ID ``<type>-<MAC>``. mDNS carries it in the TXT
records; DHCP only has the lower-cased host name (the same ID) and the MAC, which is enough to
match the device without talking to it. That matters because the device sends its DHCP request
before its HTTP server listens, so a DHCP flow that had to read the device would often fail
exactly when the address has just changed.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DOMAIN, LOGGER
from .remon_home_integration import (
    RemonClient,
    RemonConnectionError,
    RemonDiscovery,
    RemonDiscoveryError,
    RemonResponseError,
    RemonStatus,
    RemonUnsupportedApiError,
    device_id_from_hostname,
    family_display_name,
    mac_from_device_id,
)

# Home Assistant 2026.9 replaced voluptuous with probatio and maps ``import voluptuous`` onto it,
# so this works on every supported version. Only the type hints of the new versions name
# probatio's Schema, hence the ignores where the schema is passed in.
DATA_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class RemonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Remon device."""

    VERSION = 1

    _host: str
    _name: str

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Add a device by IP address or host name."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            status, errors = await self._async_read_device(host)
            if status is not None:
                await self.async_set_unique_id(status.id, raise_on_progress=False)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(title=status.display_name, data={CONF_HOST: host})

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA,  # type: ignore[arg-type]
                user_input,
            ),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Handle a device advertising ``_saltlevel._tcp``."""
        try:
            discovery = RemonDiscovery.from_txt(discovery_info.properties)
        except RemonDiscoveryError:
            return self.async_abort(reason="not_remon_device")
        if discovery_info.ip_address.version == 6:
            return self.async_abort(reason="ipv6_not_supported")
        if not discovery.is_supported:
            return self.async_abort(reason="unsupported_api")
        return await self._async_step_discovered(
            discovery.id, discovery_info.host, discovery.display_name
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Handle a DHCP request from a device, the fallback where mDNS does not get through.

        Matched on the host name for new devices, and on the MAC for devices already added
        (the ``registered_devices`` matcher), so a changed address is picked up either way.
        """
        device_id = device_id_from_hostname(discovery_info.hostname)
        if device_id is None:
            device_id = self._configured_device_id(format_mac(discovery_info.macaddress))
        if device_id is None:
            return self.async_abort(reason="not_remon_device")
        return await self._async_step_discovered(
            device_id, discovery_info.ip, family_display_name(device_id.rpartition("-")[0])
        )

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user add a discovered device; read it first to be sure it answers."""
        errors: dict[str, str] = {}
        if user_input is not None:
            status, errors = await self._async_read_device(self._host)
            if status is not None:
                if status.id != self.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_create_entry(
                    title=status.display_name, data={CONF_HOST: self._host}
                )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"name": self._name, "host": self._host},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host of a device, for example after giving it a fixed address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            status, errors = await self._async_read_device(host)
            if status is not None:
                await self.async_set_unique_id(status.id)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA,  # type: ignore[arg-type]
                user_input or entry.data,
            ),
            errors=errors,
        )

    async def _async_step_discovered(
        self, device_id: str, host: str, name: str
    ) -> ConfigFlowResult:
        """Update the host of a known device, or ask the user to add a new one."""
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self._name = name
        self.context["title_placeholders"] = {"name": name, "host": host}
        return await self.async_step_discovery_confirm()

    def _configured_device_id(self, mac: str) -> str | None:
        """Return the unique ID of the added device with this MAC, if any."""
        for entry in self._async_current_entries(include_ignore=False):
            if entry.unique_id is not None and mac_from_device_id(entry.unique_id) == mac:
                return entry.unique_id
        return None

    async def _async_read_device(self, host: str) -> tuple[RemonStatus | None, dict[str, str]]:
        """Read the status of the device at ``host``, or the form errors saying why not."""
        try:
            client = RemonClient(host, async_get_clientsession(self.hass))
            status = await client.get_status()
        except ValueError:
            return None, {CONF_HOST: "invalid_host"}
        except RemonConnectionError:
            return None, {"base": "cannot_connect"}
        except RemonUnsupportedApiError:
            return None, {"base": "unsupported_api"}
        except RemonResponseError:
            return None, {"base": "not_remon_device"}
        except Exception:
            LOGGER.exception("Unexpected error reading the device at %s", host)
            return None, {"base": "unknown"}
        return status, {}
