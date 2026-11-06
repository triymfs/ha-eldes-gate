"""Optional per-controller SIM number for the existing open command.

The account phone (config entry ``phone``) is only the login username.
This module never reads it. A saved override replaces ``DeviceDetail.phone``
for one controller id. With no valid override, the API value is used
unchanged, including a blank string.

The open body stays ``{"variables": {"OPN": "<output>;<sim>"}}``.
Nothing here contacts Eldes or sends a command.

This module must not import Home Assistant or the HTTP client so tests can
load it by file path.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

# Keep these literals aligned with const.py and diagnostics_data.py.
CONTROLLER_SIM_OVERRIDES_KEY = "controller_sim_overrides"
POLLING_OPTION_KEYS = ("update_interval", "open_timeout")

# ASCII digits only. ``\d`` would accept other Unicode digits.
# Optional leading "+", then 8..15 digits. No separators, so ";" cannot
# add another OPN field. The prefix is never invented or rewritten.
_SIM_RE = re.compile(r"^\+?[0-9]{8,15}\Z")
_MAX_RAW_LENGTH = 64


class SimOverrideError(Exception):
    """Raised when a proposed SIM value cannot be stored.

    ``code`` is a fixed token. The message never includes the submitted value.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_controller_sim(value: Any) -> str:
    """Return a normalized SIM string or raise ``SimOverrideError``.

    Strips only the ends. Does not add a "+", remove a "+", or insert a
    national prefix. Empty input is rejected here; the options helper treats
    a blank field as removal before calling this.
    """
    if not isinstance(value, str) or len(value) > _MAX_RAW_LENGTH:
        raise SimOverrideError("invalid_format")
    candidate = value.strip()
    if candidate == "":
        raise SimOverrideError("empty")
    if _SIM_RE.fullmatch(candidate) is None:
        raise SimOverrideError("invalid_format")
    return candidate


def _valid_stored_sim(value: Any) -> str | None:
    """Return a usable stored SIM, or None when it must not be sent."""
    try:
        return validate_controller_sim(value)
    except SimOverrideError:
        return None


def lookup_controller_sim(overrides: Any, device_id: Any) -> str | None:
    """Return the valid override for ``device_id``, else None.

    Invalid types and invalid strings are ignored so the command path falls
    back to the API value instead of raising or sending them.
    """
    if device_id is None or isinstance(device_id, bool):
        return None
    if not isinstance(device_id, (str, int)):
        return None
    if not isinstance(overrides, Mapping):
        return None
    raw = overrides.get(str(device_id))
    if raw is None and not isinstance(device_id, str):
        raw = overrides.get(device_id)
    return _valid_stored_sim(raw)


def phone_for_command(device: Any, options: Any) -> Any:
    """SIM string passed to the open command for this device.

    A valid per-device override wins. Otherwise the API ``phone`` value is
    returned with the historical ``value or ""`` rule. The account username
    is not an input and is not consulted.
    """
    api_phone: Any = None
    device_id: Any = None
    if isinstance(device, Mapping):
        api_phone = device.get("phone")
        device_id = device.get("id")
    overrides = None
    if isinstance(options, Mapping):
        overrides = options.get(CONTROLLER_SIM_OVERRIDES_KEY)
    override = lookup_controller_sim(overrides, device_id)
    if override is not None:
        return override
    return api_phone or ""


def api_phone_class(device: Any) -> str:
    """Classify the list ``phone`` field without copying its characters."""
    if not isinstance(device, Mapping) or "phone" not in device:
        return "missing"
    value = device.get("phone")
    if value is None:
        return "null"
    if isinstance(value, str):
        if value == "":
            return "empty"
        if value.strip() == "":
            return "blank"
        return "non_empty"
    return "unsupported"


def phone_attribute_summary(device: Any, options: Any) -> dict[str, Any]:
    """Entity attributes that describe the SIM source without its digits."""
    return {
        "api_phone_class": api_phone_class(device),
        "controller_sim_override_active": lookup_controller_sim(
            options.get(CONTROLLER_SIM_OVERRIDES_KEY)
            if isinstance(options, Mapping)
            else None,
            device.get("id") if isinstance(device, Mapping) else None,
        )
        is not None,
    }


def redact_controller_sim(text: str, controller_sim: Any) -> str:
    """Remove a resolved SIM from an error string. Short values are left as-is."""
    if not isinstance(text, str) or not isinstance(controller_sim, str):
        return text
    if len(controller_sim) < 8 or controller_sim not in text:
        return text
    return text.replace(controller_sim, "[redacted]")


def build_open_command_body(output_number: int, controller_sim: Any) -> dict[str, Any]:
    """Build the open POST body. Output number and ``;`` layout are unchanged."""
    opn = f"{int(output_number)};{controller_sim or ''}"
    return {"variables": {"OPN": opn}}


def copy_options(options: Any) -> dict[str, Any]:
    """Shallow-copy options, duplicating the override map so callers can edit."""
    if not isinstance(options, Mapping):
        return {}
    copied: dict[str, Any] = {}
    for key, value in options.items():
        if key == CONTROLLER_SIM_OVERRIDES_KEY and isinstance(value, Mapping):
            copied[key] = {
                str(device_key): device_value
                for device_key, device_value in value.items()
            }
        else:
            copied[key] = value
    return copied


def merge_polling_options(options: Any, user_input: Any) -> dict[str, Any]:
    """Apply only the polling keys from a form. Overrides are preserved.

    Extra keys in ``user_input`` (including another override map or the
    account phone) are ignored.
    """
    merged = copy_options(options)
    if not isinstance(user_input, Mapping):
        return merged
    for key in POLLING_OPTION_KEYS:
        if key in user_input:
            merged[key] = user_input[key]
    return merged


def _blank_field(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def apply_controller_sim_change(
    options: Any,
    device_id: Any,
    raw_phone: Any,
    *,
    clear: bool = False,
) -> dict[str, Any]:
    """Return new options with one controller's override set or removed.

    Does not mutate ``options``. ``clear`` or a blank field removes only
    that controller. An invalid number raises ``SimOverrideError`` and
    nothing is returned. Polling keys and other controllers stay in place.
    """
    if isinstance(device_id, bool) or not isinstance(device_id, (str, int)):
        raise SimOverrideError("unknown_controller")
    key = str(device_id).strip()
    if key == "" or key.endswith("_account"):
        raise SimOverrideError("unknown_controller")

    updated = copy_options(options)
    current = updated.get(CONTROLLER_SIM_OVERRIDES_KEY)
    overrides = dict(current) if isinstance(current, Mapping) else {}

    if clear or _blank_field(raw_phone):
        overrides.pop(key, None)
    else:
        overrides[key] = validate_controller_sim(raw_phone)

    if overrides:
        updated[CONTROLLER_SIM_OVERRIDES_KEY] = overrides
    else:
        updated.pop(CONTROLLER_SIM_OVERRIDES_KEY, None)
    return updated
