"""Home Assistant diagnostics download for Eldes Gate.

Reads the device list already held by the coordinator. Does not refresh,
does not call the Eldes API, and does not send a gate command. The payload
is built by ``diagnostics_data``, which keeps values and unknown keys out
of the file.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_OPEN_TIMEOUT, CONF_UPDATE_INTERVAL, DOMAIN
from .diagnostics_data import (
    build_config_entry_diagnostics,
    build_device_diagnostics,
)


def _stored_devices(coordinator: Any) -> Any:
    if coordinator is None:
        return None
    data = getattr(coordinator, "data", None)
    if data is None:
        return None
    return getattr(data, "devices", None)


def _options(entry: ConfigEntry) -> dict[str, Any]:
    """Copy only the non-secret option keys the flow actually stores."""
    options = getattr(entry, "options", {}) or {}
    picked: dict[str, Any] = {}
    for key in (CONF_UPDATE_INTERVAL, CONF_OPEN_TIMEOUT):
        if key in options:
            picked[key] = options[key]
    return picked


def _coordinator(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    return hass.data.get(DOMAIN, {}).get(entry.entry_id)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for the whole config entry."""
    coordinator = _coordinator(hass, entry)
    return build_config_entry_diagnostics(
        _stored_devices(coordinator), options=_options(entry)
    )


def _registry_identifier(device: Any) -> str | None:
    identifiers = getattr(device, "identifiers", ()) or ()
    for item in identifiers:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        domain, identifier = item[0], item[1]
        if domain == DOMAIN and identifier is not None:
            return str(identifier)
    return None


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: Any
) -> dict[str, Any]:
    """Return redacted diagnostics for one device page download.

    Home Assistant puts the device's display name in the downloaded file
    name. The synthetic Eldes Account device name contains the login phone,
    so that page should not be used when the file will be shared. The JSON
    body from this function still omits that phone.
    """
    coordinator = _coordinator(hass, entry)
    return build_device_diagnostics(
        _stored_devices(coordinator),
        _registry_identifier(device),
        options=_options(entry),
    )
