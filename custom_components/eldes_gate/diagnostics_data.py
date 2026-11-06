"""Redacted summary of the device list already stored in memory.

Imported by Home Assistant diagnostics and by offline tests. This module
must not import Home Assistant, ``requests``, or the API client, and it
must not read credentials. Callers pass the ``devices`` list from the last
coordinator refresh. Nothing here contacts Eldes or sends a gate command.

Arbitrary JSON keys and values can themselves be personal data, so the
result is built only from fixed key names. Unknown keys contribute counts,
never their names or values.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

DIAGNOSTIC_VERSION = 1
SOURCE = "coordinator_device_list"

# Names the integration already reads, plus a fixed checklist of phone-like
# and output-like names. A "missing" result means that exact key was not in
# the stored object. It is not a claim about the controller's configuration.
PHONE_CANDIDATE_KEYS: tuple[str, ...] = (
    "phone",
    "device_phone",
    "devicePhone",
    "phone_number",
    "phoneNumber",
    "sim",
    "sim_phone",
    "simPhone",
    "sim_number",
    "simNumber",
    "msisdn",
    "gsm",
    "gsm_phone",
    "gsmPhone",
    "mobile",
    "mobile_phone",
    "mobilePhone",
    "telephone",
    "tel",
)

DEVICE_FIELD_KEYS: tuple[str, ...] = (
    "id",
    "name",
    "imei",
    "model_id",
    "is_alive",
    "status",
    "updated_at",
)

OUTPUT_FIELD_KEYS: tuple[str, ...] = (
    "number",
    "control_name",
    "zone_name",
    "name",
    "id",
    "pulse",
    "pulse_time",
    "pulse_duration",
    "duration",
    "type",
    "mode",
    "output_type",
    "enabled",
)

_SAFE_OPTION_KEYS: tuple[str, ...] = ("update_interval", "open_timeout")

_PHONE_CANDIDATE_SET = frozenset(PHONE_CANDIDATE_KEYS)
_DEVICE_STRUCTURAL = frozenset(DEVICE_FIELD_KEYS) | _PHONE_CANDIDATE_SET | {
    "outputs"
}
_OUTPUT_STRUCTURAL = frozenset(OUTPUT_FIELD_KEYS) | _PHONE_CANDIDATE_SET

# ``sim`` and ``tel`` match only as their own segments, so a word such as
# "simple" is not treated as a phone-like key name.
_PHONE_NAME_RE = re.compile(
    r"phone|msisdn|mobile|gsm|(?:^|[_\-])sim(?:$|[_\-])|(?:^|[_\-])tel(?:$|[_\-])",
    re.IGNORECASE,
)
_DIGIT_NAME_RE = re.compile(r"^\+?\d{6,}$")
_UUID_NAME_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_PHONE_VALUE_RE = re.compile(r"\+?\d{8,15}")
_PHONE_SEPARATOR_RE = re.compile(r"[\s().\-]")

_MAX_CHILD_SCAN = 50
_MAX_SAFE_INT = 10000

_UNLISTED_PHONE_COUNT_KEYS = (
    "unlisted_phone_like_key_name_count",
    "unlisted_digit_like_key_name_count",
    "unlisted_phone_shaped_value_count",
    "nested_unlisted_phone_like_key_name_count",
    "nested_unlisted_digit_like_key_name_count",
    "nested_unlisted_phone_shaped_value_count",
)

HOW_TO_READ = (
    "devices[].phone.class is the exact key the open command reads: "
    "missing (key absent), null (JSON null), empty (''), blank (whitespace "
    "only), or non_empty. alternate_allowlisted_phone_field_present is true "
    "when another name from the fixed candidate list exists on the device, "
    "on an output, or one level inside a candidate value. "
    "possible_unlisted_phone_field is true when some other key has a "
    "phone-like name, a digit-like name, or a phone-shaped value; that name "
    "and value are not included. char_length and digit_count describe a "
    "value without reproducing it. safe_fields copies only a bool is_alive "
    "and small integers (model id, status, output number). This report uses "
    "the device list already stored by the integration. It does not contact "
    "Eldes and does not send a gate command."
)

NOTES: tuple[str, ...] = (
    "Personal values, device names, identifiers, credentials, tokens, and "
    "unknown JSON keys are omitted.",
    "A candidate listed as missing was checked and was not present under "
    "that exact name.",
    "Open-command behavior is unchanged.",
)


def build_config_entry_diagnostics(
    devices: Any, options: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Summarize every stored device for the integration diagnostics download."""
    return _build(devices, options=options, scope="config_entry", device_matched=None)


def build_device_diagnostics(
    devices: Any,
    identifier: Any,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize one stored device selected by a registry identifier.

    The identifier is compared to ``device["id"]`` and is never copied into
    the result. Identifiers ending in ``_account`` belong to the synthetic
    account device and do not match a controller.
    """
    selected, matched = _select_device(devices, identifier)
    return _build(
        selected, options=options, scope="device", device_matched=matched
    )


def _build(
    devices: Any,
    *,
    options: Mapping[str, Any] | None,
    scope: str,
    device_matched: bool | None,
) -> dict[str, Any]:
    items, skipped, payload_was_list = _coerce_devices(devices)
    summarized = [
        _summarize_device(device, index) for index, device in enumerate(items)
    ]
    result: dict[str, Any] = {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "source": SOURCE,
        "scope": scope,
        "how_to_read": HOW_TO_READ,
        "notes": list(NOTES),
        "payload_was_list": payload_was_list,
        "skipped_non_object": skipped,
        "device_count": len(summarized),
        "options": _safe_options(options),
        "devices": summarized,
    }
    if device_matched is not None:
        result["device_matched"] = device_matched
        if not device_matched:
            result["reason"] = "no_controller_in_last_device_list"
    return result


def _select_device(devices: Any, identifier: Any) -> tuple[list[Any], bool]:
    if not isinstance(identifier, str) or identifier.endswith("_account"):
        return [], False
    if not isinstance(devices, list):
        return [], False
    for device in devices:
        if (
            isinstance(device, dict)
            and "id" in device
            and str(device.get("id")) == identifier
        ):
            return [device], True
    return [], False


def _coerce_devices(devices: Any) -> tuple[list[dict[str, Any]], int, bool]:
    if not isinstance(devices, list):
        return [], 0, False
    items: list[dict[str, Any]] = []
    skipped = 0
    for item in devices:
        if isinstance(item, dict):
            items.append(item)
        else:
            skipped += 1
    return items, skipped, True


def _safe_options(options: Mapping[str, Any] | None) -> dict[str, int]:
    if not isinstance(options, Mapping):
        return {}
    safe: dict[str, int] = {}
    for key in _SAFE_OPTION_KEYS:
        if key not in options:
            continue
        value = _small_int(options.get(key))
        if value is not None:
            safe[key] = value
    return safe


def _summarize_device(device: Mapping[str, Any], index: int) -> dict[str, Any]:
    phone_candidates = _candidate_report(device)
    outputs = _summarize_outputs(device)
    unlisted = _unlisted_stats(device, structural=_DEVICE_STRUCTURAL)
    return {
        "index": index,
        "phone": _classify_key(device, "phone"),
        "phone_candidates": phone_candidates,
        "alternate_allowlisted_phone_field_present": _alternate_present(
            phone_candidates, outputs
        ),
        "possible_unlisted_phone_field": _possible_unlisted(
            unlisted, outputs, phone_candidates
        ),
        "safe_fields": _device_safe_fields(device),
        "field_shapes": {
            key: _classify_key(device, key) for key in DEVICE_FIELD_KEYS
        },
        "outputs": outputs,
        **unlisted,
    }


def _device_safe_fields(device: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    if "model_id" in device:
        model_id = _small_int(device.get("model_id"))
        if model_id is not None:
            safe["model_id"] = model_id
    if isinstance(device.get("is_alive"), bool):
        safe["is_alive"] = device["is_alive"]
    if "status" in device:
        status = _small_int(device.get("status"))
        if status is not None:
            safe["status"] = status
    return safe


def _summarize_outputs(device: Mapping[str, Any]) -> dict[str, Any]:
    if "outputs" not in device:
        return {
            "shape": _missing(),
            "items": [],
            "skipped_non_object": 0,
            "scan_capped": False,
        }
    outputs = device.get("outputs")
    if not isinstance(outputs, list):
        return {
            "shape": _present_classification(outputs),
            "items": [],
            "skipped_non_object": 0,
            "scan_capped": False,
        }

    items: list[dict[str, Any]] = []
    skipped = 0
    scan_capped = False
    for raw in outputs:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        if len(items) >= _MAX_CHILD_SCAN:
            scan_capped = True
            break
        items.append(_summarize_output(raw, len(items)))
    return {
        "shape": _present_classification(outputs),
        "items": items,
        "skipped_non_object": skipped,
        "scan_capped": scan_capped,
    }


def _summarize_output(output: Mapping[str, Any], index: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "index": index,
        "field_shapes": {
            key: _classify_key(output, key) for key in OUTPUT_FIELD_KEYS
        },
        "phone_candidates": _candidate_report(output),
        **_unlisted_stats(output, structural=_OUTPUT_STRUCTURAL),
    }
    if "number" in output:
        number = _small_int(output.get("number"))
        if number is not None:
            item["number"] = number
    return item


def _candidate_report(container: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _classify_key(container, key) for key in PHONE_CANDIDATE_KEYS}


def _classify_key(container: Mapping[str, Any], key: str) -> dict[str, Any]:
    if key not in container:
        return _missing()
    value = container[key]
    info = _present_classification(value)
    if isinstance(value, dict):
        info.update(_nested_mapping_stats(value))
    return info


def _missing() -> dict[str, Any]:
    return {"present": False, "class": "missing"}


def _present_classification(value: Any) -> dict[str, Any]:
    if value is None:
        return {"present": True, "type": "null", "class": "null"}
    if isinstance(value, bool):
        return {"present": True, "type": "bool", "class": "non_empty"}
    if isinstance(value, str):
        stripped = value.strip()
        if value == "":
            klass = "empty"
        elif stripped == "":
            klass = "blank"
        else:
            klass = "non_empty"
        digit_count = sum(character.isdigit() for character in value)
        return {
            "present": True,
            "type": "str",
            "class": klass,
            "char_length": len(value),
            "stripped_length": len(stripped),
            "digit_count": digit_count,
            "has_digit": digit_count > 0,
        }
    if isinstance(value, int):
        return {
            "present": True,
            "type": "int",
            "class": "non_empty",
            "digit_count": len(str(abs(value))),
        }
    if isinstance(value, float):
        return {"present": True, "type": "float", "class": "non_empty"}
    if isinstance(value, (bytes, bytearray)):
        return {
            "present": True,
            "type": "bytes",
            "class": "empty" if len(value) == 0 else "non_empty",
            "byte_length": len(value),
        }
    if isinstance(value, list):
        return {
            "present": True,
            "type": "list",
            "class": "empty" if len(value) == 0 else "non_empty",
            "item_count": len(value),
        }
    if isinstance(value, dict):
        return {
            "present": True,
            "type": "dict",
            "class": "empty" if len(value) == 0 else "non_empty",
            "key_count": len(value),
        }
    return {"present": True, "type": "other", "class": "non_empty"}


def _nested_mapping_stats(value: Mapping[str, Any]) -> dict[str, Any]:
    nested: dict[str, Any] = {}
    unlisted = 0
    phone_names = 0
    digit_names = 0
    identifier_names = 0
    phone_values = 0
    scan_capped = False
    for seen, (key, child) in enumerate(value.items()):
        if seen >= _MAX_CHILD_SCAN:
            scan_capped = True
            break
        if isinstance(key, str) and key in _PHONE_CANDIDATE_SET:
            nested[key] = _present_classification(child)
            continue
        unlisted += 1
        if isinstance(key, str) and _PHONE_NAME_RE.search(key):
            phone_names += 1
        if isinstance(key, str) and _DIGIT_NAME_RE.fullmatch(key):
            digit_names += 1
        elif isinstance(key, str) and _identifier_like_name(key):
            identifier_names += 1
        phone_values += _phone_shaped_count(child, depth=1)
    return {
        "nested_allowlisted_phone_fields": nested,
        "nested_unlisted_key_count": unlisted,
        "nested_unlisted_phone_like_key_name_count": phone_names,
        "nested_unlisted_digit_like_key_name_count": digit_names,
        "nested_unlisted_identifier_like_key_name_count": identifier_names,
        "nested_unlisted_phone_shaped_value_count": phone_values,
        "nested_scan_capped": scan_capped,
    }


def _unlisted_stats(
    container: Mapping[str, Any], *, structural: frozenset[str]
) -> dict[str, Any]:
    unlisted = 0
    phone_names = 0
    digit_names = 0
    identifier_names = 0
    phone_values = 0
    scan_capped = False
    inspected = 0
    for key, value in container.items():
        if isinstance(key, str) and key in structural:
            continue
        unlisted += 1
        if isinstance(key, str) and _PHONE_NAME_RE.search(key):
            phone_names += 1
        if isinstance(key, str) and _DIGIT_NAME_RE.fullmatch(key):
            digit_names += 1
        elif isinstance(key, str) and _identifier_like_name(key):
            identifier_names += 1
        if inspected >= _MAX_CHILD_SCAN:
            scan_capped = True
            continue
        inspected += 1
        phone_values += _phone_shaped_count(value, depth=0)
    stats: dict[str, Any] = {
        "unlisted_key_count": unlisted,
        "unlisted_phone_like_key_name_count": phone_names,
        "unlisted_digit_like_key_name_count": digit_names,
        "unlisted_identifier_like_key_name_count": identifier_names,
        "unlisted_phone_shaped_value_count": phone_values,
    }
    if scan_capped:
        stats["scan_capped"] = True
    return stats


def _phone_shaped_count(value: Any, *, depth: int) -> int:
    if _looks_like_phone_value(value):
        return 1
    if depth >= 1:
        return 0
    count = 0
    children: Any
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return 0
    for seen, child in enumerate(children):
        if seen >= _MAX_CHILD_SCAN:
            break
        if _looks_like_phone_value(child):
            count += 1
    return count


def _looks_like_phone_value(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        return 8 <= len(str(abs(value))) <= 15
    if isinstance(value, str):
        compact = _PHONE_SEPARATOR_RE.sub("", value.strip())
        return _PHONE_VALUE_RE.fullmatch(compact) is not None
    return False


def _identifier_like_name(key: str) -> bool:
    """True for UUID-like or email-like key names. Digit strings are separate."""
    return bool(_UUID_NAME_RE.fullmatch(key) or "@" in key)


def _alternate_present(
    phone_candidates: Mapping[str, Any], outputs: Mapping[str, Any]
) -> bool:
    for key, info in phone_candidates.items():
        if key == "phone":
            if _nested_candidate_present(info):
                return True
            continue
        if info.get("present") or _nested_candidate_present(info):
            return True
    for item in outputs.get("items") or []:
        for info in (item.get("phone_candidates") or {}).values():
            if info.get("present") or _nested_candidate_present(info):
                return True
    return False


def _nested_candidate_present(info: Mapping[str, Any]) -> bool:
    nested = info.get("nested_allowlisted_phone_fields") or {}
    return any(child.get("present") for child in nested.values())


def _possible_unlisted(
    unlisted: Mapping[str, Any],
    outputs: Mapping[str, Any],
    phone_candidates: Mapping[str, Any],
) -> bool:
    if _counts_suggest_phone(unlisted):
        return True
    for info in phone_candidates.values():
        if _counts_suggest_phone(info):
            return True
    for item in outputs.get("items") or []:
        if _counts_suggest_phone(item):
            return True
        for info in (item.get("phone_candidates") or {}).values():
            if _counts_suggest_phone(info):
                return True
    return False


def _counts_suggest_phone(stats: Mapping[str, Any]) -> bool:
    return any(stats.get(key, 0) for key in _UNLISTED_PHONE_COUNT_KEYS)


def _small_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if abs(value) > _MAX_SAFE_INT:
        return None
    return value
