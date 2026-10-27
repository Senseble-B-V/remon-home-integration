# Remon for Home Assistant

Home Assistant integration for **Remon** salt level monitors (SaltBuddy and Remon
Waterontharder), installed through **HACS**. Devices are discovered on the LAN (mDNS, with DHCP as
fallback) and added with one click: salt level, leak and salt sensor error, with no broker,
credentials or YAML.

All traffic stays on your LAN. The device API is read-only and needs no credentials.

Requires Home Assistant 2025.3 or newer.

## Installation

Add this repository to HACS once:

1. In Home Assistant, open **HACS**, then the three-dot menu > **Custom repositories**.
2. Add `https://github.com/Senseble-B-V/remon-home-integration` with type **Integration**.
3. Search HACS for **Remon**, select **Download**, and restart Home Assistant.

Report problems at [GitHub issues](https://github.com/Senseble-B-V/remon-home-integration/issues).

## Adding a device

Devices on the same network as Home Assistant show up under Settings > Devices & services as
discovered; select **Add** to confirm. Discovery has two paths:

- **mDNS (zeroconf):** the device advertises `_saltlevel._tcp` with its ID in the TXT records.
- **DHCP (fallback):** for networks where multicast does not reach Home Assistant (VLANs, some
  mesh Wi-Fi), the device is recognised by its DHCP host name `SaltBuddy-<MAC>`,
  `Softener-<MAC>` or `SoftenerDF-<MAC>`. Home Assistant only sees DHCP requests if it runs on
  the host network (Home Assistant OS does).

Both paths also update the address of a device that is already added, so a new IP from the
router needs no action. A device that is not discovered can be added by hand with **Add
integration > Remon** and its IP address or `<id>.local` name; **Reconfigure** changes it later.

The device is polled every 60 seconds, so a leak shows in Home Assistant within about a minute. It is a device named after its family ("SaltBuddy" or
"Remon Waterontharder") with these entities:

| Entity | Type | Meaning |
|---|---|---|
| Salt level | sensor, % | Unknown while the salt sensor has no reading or reports a fault |
| Leak | binary sensor, moisture | Water detected at the device |
| Salt sensor | binary sensor, problem (diagnostic) | The salt level sensor reports a fault |

## Repository layout

```
custom_components/remon/              what HACS installs into Home Assistant
  remon_home_integration/             bundled device client (no Home Assistant imports)
blueprints/automation/remon/          optional automation blueprint (not installed by HACS)
tests/                                client tests against recorded device responses
tests_ha/                             integration tests (Home Assistant's pytest plugin)
```

HACS copies only `custom_components/remon/` into Home Assistant, so the client is bundled there
instead of being installed from PyPI. It uses only `aiohttp` and `yarl`, which ship with Home
Assistant.

## Automation blueprint

The integration only adds the entities; Home Assistant sends no notifications until you create an
automation. `blueprints/automation/remon/salt_level_and_leak_alerts.yaml` is a ready-made one: it
notifies a phone with the Home Assistant app when the salt level drops below a threshold you
choose and when a leak is detected. Its entity pickers only offer entities of this integration.

Import it under Settings > Automations & scenes > Blueprints > Import blueprint with the URL
`https://github.com/Senseble-B-V/remon-home-integration/blob/main/blueprints/automation/remon/salt_level_and_leak_alerts.yaml`,
or copy the file to `<config>/blueprints/automation/remon/` and reload automations.
Then create an automation from it and pick the Salt level sensor, the Leak sensor and the phone.

## Check a device without Home Assistant

From any machine on the same LAN, with [uv](https://docs.astral.sh/uv/) installed:

```sh
cd custom_components/remon
uv run python -m remon_home_integration 192.168.1.42    # or SaltBuddy-a1b2c3d4e5f6.local
```

A healthy device prints its validated status as JSON; on a connection or contract problem the
command prints `error: ...` and exits with status 1. For the raw response without validation:
`curl http://192.168.1.42/api/status`.

### Status

`get_status()` returns a frozen `RemonStatus`:

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | `<type>-<MAC>`, for example `SaltBuddy-a1b2c3d4e5f6`. Stable; use it as unique ID |
| `type` | `str` | Internal firmware type (`SaltBuddy`, `Softener`, `SoftenerDF`). Do not show it to users |
| `fw` | `str` | Firmware version: a short git commit hash, compare for equality only |
| `salt_level` | `int \| None` | 0 to 100 percent; `None` until the sensor has its first sample |
| `sensor_error` | `bool` | The salt level sensor reports a fault (also true while it has no sample) |
| `leak` | `bool` | A water leak is detected |
| `api` | `int \| None` | Contract version; `None` on firmware that does not report it yet |
| `display_name` | `str` | User-facing name: "SaltBuddy", "Remon Waterontharder" or "Remon device" |
| `mac` | `str \| None` | `aa:bb:cc:dd:ee:ff`, derived from `id` |

### Errors

All errors derive from `RemonError`:

| Error | When |
|---|---|
| `RemonConnectionError` | Timeout, connection refused, DNS failure, connection dropped |
| `RemonResponseError` | Non-200 answer, body that is not JSON, or a missing or mistyped field |
| `RemonUnsupportedApiError` | Firmware reports a newer `api` version than this integration supports (subclass of `RemonResponseError`) |
| `RemonDiscoveryError` | mDNS TXT records without a valid `id` |

## Device API

```
GET http://<device>/api/status
```

```json
{"id":"SaltBuddy-a1b2c3d4e5f6","type":"SaltBuddy","fw":"382de8e","salt_level":64,"sensor_error":false,"leak":false}
```