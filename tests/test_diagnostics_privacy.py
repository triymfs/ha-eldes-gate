"""Offline checks that device-list diagnostics never emit private values.

The integration package imports Home Assistant, so the pure summarizer is
loaded by file path. No network and no Home Assistant install are required.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = (
    ROOT / "custom_components" / "eldes_gate" / "diagnostics_data.py"
)
DIAG_PATH = ROOT / "custom_components" / "eldes_gate" / "diagnostics.py"

PHONE = "+37061234567"
PHONE_DIGITS = "37061234567"
PHONE_SPACED = "+370 612 34567"
IMEI = "490154203237518"
GATE_NAME = "Gate behind the blue house"
EMAIL = "user.private@example.com"
PASSWORD = "hunter2-password"
UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TOKEN = "ghp_FAKESUPERSECRETTOKEN1234567890"
CONTROL_NAME = "Open/Close Secret Label"
ZONE_NAME = "Zone1 Private Yard"
NESTED_OWNER = "Alice Example"
OUTPUT_MSISDN = "+37060001122"
NESTED_PHONE = "+37060002233"
KEY_AS_PHONE = "+37069876543"
UNLISTED_PHONE_VALUE = "+37061112233"
REPR_LEAK = "LEAKED-REPR-999"
DEVICE_ID = "dev-999-SHOULD-NOT-LEAK"

FORBIDDEN = (
    PHONE,
    PHONE_DIGITS,
    PHONE_SPACED,
    IMEI,
    GATE_NAME,
    EMAIL,
    PASSWORD,
    UUID,
    TOKEN,
    CONTROL_NAME,
    ZONE_NAME,
    NESTED_OWNER,
    OUTPUT_MSISDN,
    NESTED_PHONE,
    KEY_AS_PHONE,
    UNLISTED_PHONE_VALUE,
    REPR_LEAK,
    DEVICE_ID,
    "hidden-value-ZZTOP",
    "not-a-shape-but-name",
    "contractor_phone",
    "simple_mode",
    "api_token",
    "owner_email",
    "Bearer super-token",
    "drop table",
    "1.5",
    "+15555550199",
    "15555550199",
)


def _load_data():
    before = set(sys.modules)
    spec = importlib.util.spec_from_file_location(
        "eldes_diagnostics_data_under_test", DATA_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    loaded = set(sys.modules) - before
    assert not any(name.split(".")[0] in {"homeassistant", "requests"} for name in loaded)
    return module


DATA = _load_data()


def _walk(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
    else:
        yield value


def assert_redacted(payload) -> None:
    """Every string is from the fixed vocabulary, and no secret integer leaks."""
    allowed_values = {
        DATA.HOW_TO_READ,
        DATA.SOURCE,
        "config_entry",
        "device",
        "no_controller_in_last_device_list",
        "missing",
        "null",
        "empty",
        "blank",
        "non_empty",
        "bool",
        "str",
        "int",
        "float",
        "bytes",
        "list",
        "dict",
        "other",
        *DATA.NOTES,
    }
    allowed_keys = {
        "diagnostic_version",
        "source",
        "scope",
        "how_to_read",
        "notes",
        "payload_was_list",
        "skipped_non_object",
        "device_count",
        "options",
        "devices",
        "device_matched",
        "reason",
        "index",
        "phone",
        "phone_candidates",
        "alternate_allowlisted_phone_field_present",
        "possible_unlisted_phone_field",
        "safe_fields",
        "field_shapes",
        "outputs",
        "shape",
        "items",
        "scan_capped",
        "number",
        "present",
        "class",
        "type",
        "char_length",
        "stripped_length",
        "digit_count",
        "has_digit",
        "item_count",
        "key_count",
        "byte_length",
        "nested_allowlisted_phone_fields",
        "nested_unlisted_key_count",
        "nested_unlisted_phone_like_key_name_count",
        "nested_unlisted_digit_like_key_name_count",
        "nested_unlisted_identifier_like_key_name_count",
        "nested_unlisted_phone_shaped_value_count",
        "nested_scan_capped",
        "unlisted_key_count",
        "unlisted_phone_like_key_name_count",
        "unlisted_digit_like_key_name_count",
        "unlisted_identifier_like_key_name_count",
        "unlisted_phone_shaped_value_count",
        "model_id",
        "is_alive",
        "status",
        "update_interval",
        "open_timeout",
        "controller_sim_override_count",
        *DATA.PHONE_CANDIDATE_KEYS,
        *DATA.DEVICE_FIELD_KEYS,
        *DATA.OUTPUT_FIELD_KEYS,
    }
    for item in _walk(payload):
        if isinstance(item, str):
            assert item in allowed_values or item in allowed_keys
        elif isinstance(item, bool) or item is None:
            continue
        elif isinstance(item, int):
            assert 0 <= item <= 10000
        else:
            raise AssertionError(f"unexpected value type {type(item)!r}")

    text = json.dumps(payload)
    for secret in FORBIDDEN:
        assert secret not in text
    for digits in (PHONE_DIGITS, IMEI, "37060001122", "37060002233", "37069876543", "37061112233"):
        for offset in range(len(digits) - 3):
            assert digits[offset : offset + 4] not in text


class _ReprSecret:
    def __repr__(self) -> str:
        return REPR_LEAK


def _sensitive_device() -> dict:
    return {
        "id": DEVICE_ID,
        "name": GATE_NAME,
        "imei": IMEI,
        "phone": PHONE,
        "model_id": 14,
        "is_alive": True,
        "status": 2,
        "updated_at": "2026-01-01T00:00:00Z",
        "owner_email": EMAIL,
        "api_token": TOKEN,
        "note": f"password={PASSWORD} uuid={UUID} Bearer super-token",
        KEY_AS_PHONE: "hidden-value-ZZTOP",
        "simple_mode": "drop table",
        "contractor_phone": "not-a-shape-but-name",
        "comment": UNLISTED_PHONE_VALUE,
        "ratio": 1.5,
        "raw_phone": b"+37061234567",
        "sim": {"phone": NESTED_PHONE, "owner": NESTED_OWNER},
        UUID: "uuid-key-must-stay-hidden",
        EMAIL: "email-key-must-stay-hidden",
        "outputs": [
            {
                "number": 1,
                "control_name": CONTROL_NAME,
                "zone_name": ZONE_NAME,
                "msisdn": OUTPUT_MSISDN,
                "pulse": None,
            },
            "not-a-shape-but-name",
        ],
    }


def test_custom_object_repr_is_not_emitted():
    report = DATA.build_config_entry_diagnostics([{"weird": _ReprSecret()}])
    assert_redacted(report)
    info = report["devices"][0]["field_shapes"]["id"]
    assert info["class"] == "missing"
    assert report["devices"][0]["unlisted_key_count"] == 1
    assert report["devices"][0]["phone"]["class"] == "missing"


def test_sensitive_fixture_is_not_emitted():
    original = _sensitive_device()
    snapshot = deepcopy(original)
    report = DATA.build_config_entry_diagnostics(
        [original],
        options={
            "update_interval": 300,
            "open_timeout": 30,
            "password": PASSWORD,
            "phone": PHONE,
            "uuid": UUID,
            "update_interval_bad": "300; drop table",
            "controller_sim_overrides": {
                "ctrl-secret": "+15555550199",
                "ctrl-bad": "1;+15555550199",
            },
        },
    )
    assert original == snapshot
    assert_redacted(report)
    device = report["devices"][0]
    assert device["phone"]["class"] == "non_empty"
    assert device["phone"]["type"] == "str"
    assert device["phone"]["char_length"] == len(PHONE)
    assert device["phone"]["digit_count"] == len(PHONE_DIGITS)
    assert device["phone"]["has_digit"] is True
    assert device["safe_fields"] == {"model_id": 14, "is_alive": True, "status": 2}
    assert device["alternate_allowlisted_phone_field_present"] is True
    assert device["possible_unlisted_phone_field"] is True
    assert device["phone_candidates"]["msisdn"]["class"] == "missing"
    assert device["phone_candidates"]["sim"]["type"] == "dict"
    assert device["phone_candidates"]["sim"]["nested_allowlisted_phone_fields"]["phone"][
        "digit_count"
    ] == len("37060002233")
    assert device["unlisted_phone_like_key_name_count"] >= 1
    assert device["unlisted_digit_like_key_name_count"] >= 1
    assert device["unlisted_identifier_like_key_name_count"] >= 1
    assert device["unlisted_phone_shaped_value_count"] >= 1
    assert "contractor_phone" not in json.dumps(report)
    assert report["options"] == {"update_interval": 300, "open_timeout": 30}
    assert report["controller_sim_override_count"] == 1
    output = device["outputs"]["items"][0]
    assert output["number"] == 1
    assert output["field_shapes"]["control_name"]["class"] == "non_empty"
    assert output["field_shapes"]["control_name"]["char_length"] == len(CONTROL_NAME)
    assert output["phone_candidates"]["msisdn"]["class"] == "non_empty"
    assert output["field_shapes"]["pulse"]["class"] == "null"
    assert device["outputs"]["skipped_non_object"] == 1


@pytest.mark.parametrize(
    ("phone", "expected_class", "expected_type"),
    [
        ("__missing__", "missing", None),
        (None, "null", "null"),
        ("", "empty", "str"),
        ("   \t", "blank", "str"),
        (PHONE_SPACED, "non_empty", "str"),
        (int(PHONE_DIGITS), "non_empty", "int"),
    ],
)
def test_phone_presence_classes(phone, expected_class, expected_type):
    device = {"model_id": 14, "outputs": [{"number": 1}]}
    if phone != "__missing__":
        device["phone"] = phone
    report = DATA.build_config_entry_diagnostics([device])
    assert_redacted(report)
    info = report["devices"][0]["phone"]
    assert info["class"] == expected_class
    assert info["present"] is (expected_class != "missing")
    if expected_type is not None:
        assert info["type"] == expected_type
    if phone == "":
        assert info["char_length"] == 0
        assert info["digit_count"] == 0
    if phone == "   \t":
        assert info["stripped_length"] == 0
        assert info["has_digit"] is False
    if phone == PHONE_SPACED:
        assert info["digit_count"] == len(PHONE_DIGITS)
        assert info["char_length"] == len(PHONE_SPACED)


def test_missing_phone_with_allowlisted_alternate_on_output():
    report = DATA.build_config_entry_diagnostics(
        [{"model_id": 14, "outputs": [{"number": 1, "msisdn": OUTPUT_MSISDN}]}]
    )
    assert_redacted(report)
    device = report["devices"][0]
    assert device["phone"]["class"] == "missing"
    assert device["alternate_allowlisted_phone_field_present"] is True
    assert device["possible_unlisted_phone_field"] is False
    assert device["outputs"]["items"][0]["phone_candidates"]["msisdn"]["present"] is True


def test_phone_sized_model_id_and_output_number_are_withheld():
    huge = int(PHONE_DIGITS)
    report = DATA.build_config_entry_diagnostics(
        [{"model_id": huge, "status": huge, "outputs": [{"number": huge}]}]
    )
    assert_redacted(report)
    device = report["devices"][0]
    assert "model_id" not in device["safe_fields"]
    assert "status" not in device["safe_fields"]
    assert device["field_shapes"]["model_id"]["type"] == "int"
    assert device["field_shapes"]["model_id"]["digit_count"] == len(PHONE_DIGITS)
    assert "number" not in device["outputs"]["items"][0]


def test_simple_mode_is_not_a_phone_like_name():
    report = DATA.build_config_entry_diagnostics([{"simple_mode": "drop table"}])
    assert_redacted(report)
    device = report["devices"][0]
    assert device["unlisted_key_count"] == 1
    assert device["unlisted_phone_like_key_name_count"] == 0
    assert device["possible_unlisted_phone_field"] is False


def test_uuid_key_is_counted_without_raising_the_phone_flag():
    report = DATA.build_config_entry_diagnostics([{UUID: "uuid-key-must-stay-hidden"}])
    assert_redacted(report)
    device = report["devices"][0]
    assert device["unlisted_identifier_like_key_name_count"] == 1
    assert device["possible_unlisted_phone_field"] is False


def test_non_dict_and_non_list_payloads_are_dropped():
    report = DATA.build_config_entry_diagnostics([PHONE, {"model_id": 14}])
    assert_redacted(report)
    assert report["skipped_non_object"] == 1
    assert report["device_count"] == 1

    foreign = DATA.build_config_entry_diagnostics(PHONE)
    assert_redacted(foreign)
    assert foreign["payload_was_list"] is False
    assert foreign["device_count"] == 0


def test_device_selection_does_not_echo_identifier_or_siblings():
    devices = [
        _sensitive_device(),
        {"id": "other-device-SHOULD-NOT-LEAK", "phone": "+37065550000", "name": "Other"},
    ]
    matched = DATA.build_device_diagnostics(devices, DEVICE_ID)
    assert_redacted(matched)
    assert matched["device_matched"] is True
    assert matched["device_count"] == 1
    assert matched["scope"] == "device"
    assert "other-device-SHOULD-NOT-LEAK" not in json.dumps(matched)
    assert "+37065550000" not in json.dumps(matched)

    account = DATA.build_device_diagnostics(devices, "entry_account")
    assert_redacted(account)
    assert account["device_matched"] is False
    assert account["reason"] == "no_controller_in_last_device_list"
    assert account["device_count"] == 0
    assert PHONE not in json.dumps(account)

    missing = DATA.build_device_diagnostics(devices, "does-not-exist")
    assert_redacted(missing)
    assert missing["device_matched"] is False
    assert missing["devices"] == []


def test_outputs_missing_and_null_differ():
    missing = DATA.build_config_entry_diagnostics([{"model_id": 14}])
    explicit = DATA.build_config_entry_diagnostics([{"model_id": 14, "outputs": None}])
    assert_redacted(missing)
    assert_redacted(explicit)
    assert missing["devices"][0]["outputs"]["shape"]["class"] == "missing"
    assert explicit["devices"][0]["outputs"]["shape"]["class"] == "null"
    assert explicit["devices"][0]["outputs"]["shape"]["present"] is True


def test_checked_output_fields_report_missing_without_values():
    report = DATA.build_config_entry_diagnostics(
        [{"outputs": [{"number": 1, "control_name": CONTROL_NAME}]}]
    )
    assert_redacted(report)
    shapes = report["devices"][0]["outputs"]["items"][0]["field_shapes"]
    assert shapes["pulse"]["class"] == "missing"
    assert shapes["duration"]["class"] == "missing"
    assert shapes["zone_name"]["class"] == "missing"
    assert shapes["control_name"]["char_length"] == len(CONTROL_NAME)


def test_diagnostics_module_does_not_call_the_api():
    source = DIAG_PATH.read_text(encoding="utf-8")
    data_source = DATA_PATH.read_text(encoding="utf-8")
    for text in (source, data_source):
        for forbidden in (
            "send_open",
            "list_devices",
            "import requests",
            "async_request_refresh",
            "entry.data",
            "CONF_PASSWORD",
            "CONF_PHONE",
            "CONF_UUID",
            "access_token",
        ):
            assert forbidden not in text
    assert "async_get_config_entry_diagnostics" in source
    assert "async_get_device_diagnostics" in source
    assert "from homeassistant" in source
    assert "homeassistant" not in data_source
