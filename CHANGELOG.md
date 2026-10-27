# Changelog

Releases are [GitHub releases](https://github.com/Senseble-B-V/remon-home-integration/releases)
tagged `vX.Y.Z`, matching `version` in `custom_components/remon/manifest.json`. HACS offers each
release as an update.

## Unreleased

- Home Assistant integration (`custom_components/remon`, version 0.1.0, Home Assistant 2025.3 or
  newer): config flow with mDNS discovery of `_saltlevel._tcp`, DHCP discovery as fallback (host
  names `saltbuddy-*`, `softener-*`, `softenerdf-*` and already added devices by MAC), manual
  host entry and reconfigure. Discovery also updates the address of an added device.
- Entities: Salt level sensor (unknown while the salt sensor reports a fault), Leak binary sensor
  (moisture) and Salt sensor binary sensor (problem, diagnostic). Polled every 60 s; the device's
  firmware version updates on the device page without a reload.
- English and Dutch translations.
- Client: `device_id_from_hostname()` restores the device ID from a lower-cased DHCP host name.
- Bundled client `remon_home_integration`: `RemonClient.get_status()` reads `GET /api/status`
  with strict validation of the LAN status contract.
- `RemonStatus` and `RemonDiscovery` (mDNS TXT records) models, `family_display_name()`,
  `mac_from_device_id()`.
- Errors: `RemonConnectionError`, `RemonResponseError`, `RemonUnsupportedApiError`,
  `RemonDiscoveryError`, all derived from `RemonError`.
- `python -m remon_home_integration <host>` to read a device without Home Assistant.
- Automation blueprint `blueprints/automation/remon/salt_level_and_leak_alerts.yaml`: phone
  notification on low salt level and on a leak (moved from the firmware repository).
