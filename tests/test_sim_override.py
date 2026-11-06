"""Offline tests for the optional per-controller SIM override.

Numbers below are synthetic fixtures. They are not real SIM numbers.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "custom_components" / "eldes_gate"
SIM_PATH = GATE / "sim_override.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "eldes_sim_override_under_test", SIM_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


SIM = _load()

SIM_A = "+15555550100"
SIM_B = "+15555550200"
ACCOUNT = "+15555550999"
KEY = SIM.CONTROLLER_SIM_OVERRIDES_KEY


def _options(overrides=None, **extra):
    base = {"update_interval": 300, "open_timeout": 30, "phone": ACCOUNT}
    if overrides is not None:
        base[KEY] = overrides
    base.update(extra)
    return base


def test_pattern_and_storage_key_stay_aligned():
    sim_source = SIM_PATH.read_text(encoding="utf-8")
    const_source = (GATE / "const.py").read_text(encoding="utf-8")
    diag_source = (GATE / "diagnostics_data.py").read_text(encoding="utf-8")
    pattern = r"^\+?[0-9]{8,15}\Z"
    assert pattern in sim_source
    assert pattern in diag_source
    assert 'CONTROLLER_SIM_OVERRIDES_KEY = "controller_sim_overrides"' in sim_source
    assert 'CONF_CONTROLLER_SIM_OVERRIDES = "controller_sim_overrides"' in const_source
    assert '_CONTROLLER_SIM_OVERRIDES_KEY = "controller_sim_overrides"' in diag_source


def test_valid_numbers_are_kept_without_a_guessed_prefix():
    assert SIM.validate_controller_sim(SIM_A) == SIM_A
    assert SIM.validate_controller_sim("  " + SIM_A + "\n") == SIM_A
    assert SIM.validate_controller_sim("15555550100") == "15555550100"
    assert SIM.validate_controller_sim("00000000") == "00000000"
    assert SIM.validate_controller_sim("1" * 15) == "1" * 15
    assert SIM.validate_controller_sim("+" + "1" * 8) == "+" + "1" * 8
    assert SIM.validate_controller_sim("+" + "1" * 15) == "+" + "1" * 15


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        None,
        15555550100,
        15.5,
        True,
        False,
        ["+15555550100"],
        {"number": SIM_A},
        b"+15555550100",
        "1" * 7,
        "1" * 16,
        "+" + "1" * 7,
        "+" + "1" * 16,
        "++15555550100",
        "+15555550100;1",
        "1;+15555550100",
        "+15555550100\nOPN",
        "+15555550100\r\n1",
        "+1555 555 0100",
        "+1(555)555-0100",
        "+1555.555.0100",
        "sim:+15555550100",
        "+15555550100#1",
        "+15555550100,1",
        "\u0661" * 8,
        "+" + "\u0661" * 8,
        "x" * 80,
    ],
)
def test_invalid_values_raise_without_echoing_the_input(value):
    with pytest.raises(SIM.SimOverrideError) as caught:
        SIM.validate_controller_sim(value)
    text = str(caught.value)
    assert caught.value.code in {"invalid_format", "empty"}
    assert text == caught.value.code
    rendered = repr(value)
    if len(rendered) > 4:
        assert rendered not in text
    if isinstance(value, str) and len(value) > 4:
        assert value not in text


def test_precedence_and_per_device_isolation():
    options = _options({"ctrl-a": SIM_A, "7": SIM_B})
    assert SIM.phone_for_command({"id": "ctrl-a", "phone": ""}, options) == SIM_A
    assert (
        SIM.phone_for_command({"id": "ctrl-a", "phone": "+15555550888"}, options)
        == SIM_A
    )
    assert SIM.phone_for_command({"id": "ctrl-b", "phone": ""}, options) == ""
    assert SIM.phone_for_command({"id": "ctrl-b", "phone": "api-value"}, options) == (
        "api-value"
    )
    assert SIM.phone_for_command({"id": 7, "phone": ""}, options) == SIM_B
    assert SIM.phone_for_command({"id": "ctrl-b", "phone": None}, options) == ""
    assert SIM.phone_for_command({"id": "ctrl-b"}, options) == ""
    # Account username lives on the "phone" option and must not be sent.
    assert ACCOUNT not in (
        SIM.phone_for_command({"id": "ctrl-b", "phone": ""}, options),
    )


def test_absent_or_invalid_override_preserves_api_value():
    assert SIM.phone_for_command({"id": "ctrl-a", "phone": ""}, {}) == ""
    assert SIM.phone_for_command({"id": "ctrl-a", "phone": "   "}, {}) == "   "
    assert SIM.phone_for_command({"id": "ctrl-a", "phone": SIM_A}, {"phone": ACCOUNT}) == (
        SIM_A
    )
    options = _options({"ctrl-a": "1;+15555550100", "ctrl-b": 15555550200})
    assert SIM.phone_for_command({"id": "ctrl-a", "phone": ""}, options) == ""
    assert SIM.phone_for_command({"id": "ctrl-b", "phone": "from-api"}, options) == (
        "from-api"
    )
    assert (
        SIM.phone_for_command(
            {"id": "ctrl-a", "phone": ""},
            {KEY: None},
        )
        == ""
    )


def test_command_body_keeps_output_mapping_and_separator():
    blank = SIM.build_open_command_body(
        1, SIM.phone_for_command({"id": "ctrl-a", "phone": ""}, {})
    )
    assert blank == {"variables": {"OPN": "1;"}}

    overridden = SIM.build_open_command_body(
        1,
        SIM.phone_for_command(
            {"id": "ctrl-a", "phone": ""},
            _options({"ctrl-a": SIM_A}),
        ),
    )
    assert overridden == {"variables": {"OPN": "1;" + SIM_A}}
    assert overridden["variables"]["OPN"].count(";") == 1

    other_output = SIM.build_open_command_body(2, SIM_A)
    assert other_output["variables"]["OPN"] == "2;" + SIM_A

    api_only = SIM.build_open_command_body(
        1, SIM.phone_for_command({"id": "ctrl-a", "phone": "   "}, {})
    )
    assert api_only["variables"]["OPN"] == "1;   "


def test_options_preserve_polling_and_isolate_removal():
    original = _options({"ctrl-a": SIM_A}, custom_flag=True)
    snapshot = deepcopy(original)

    with_b = SIM.apply_controller_sim_change(original, "ctrl-b", "  " + SIM_B + " ")
    assert original == snapshot
    assert with_b["update_interval"] == 300
    assert with_b["open_timeout"] == 30
    assert with_b["custom_flag"] is True
    assert with_b["phone"] == ACCOUNT
    assert with_b[KEY] == {"ctrl-a": SIM_A, "ctrl-b": SIM_B}

    polled = SIM.merge_polling_options(
        with_b,
        {
            "update_interval": 120,
            KEY: {"ctrl-a": ACCOUNT},
            "phone": "+15555550777",
        },
    )
    assert polled["update_interval"] == 120
    assert polled["open_timeout"] == 30
    assert polled[KEY] == {"ctrl-a": SIM_A, "ctrl-b": SIM_B}
    assert polled["phone"] == ACCOUNT

    removed = SIM.apply_controller_sim_change(
        polled, "ctrl-a", SIM_B, clear=True
    )
    assert removed[KEY] == {"ctrl-b": SIM_B}
    assert removed["update_interval"] == 120
    assert SIM.phone_for_command({"id": "ctrl-a", "phone": ""}, removed) == ""
    assert SIM.phone_for_command({"id": "ctrl-b", "phone": ""}, removed) == SIM_B

    cleared = SIM.apply_controller_sim_change(removed, "ctrl-b", "  ")
    assert KEY not in cleared
    assert cleared["update_interval"] == 120
    assert cleared["custom_flag"] is True


def test_invalid_change_does_not_mutate_or_echo():
    original = _options({"ctrl-a": SIM_A})
    snapshot = deepcopy(original)
    bad = "1;+15555550100"
    with pytest.raises(SIM.SimOverrideError) as caught:
        SIM.apply_controller_sim_change(original, "ctrl-b", bad)
    assert original == snapshot
    assert bad not in str(caught.value)
    assert caught.value.code == "invalid_format"


def test_attributes_do_not_include_the_sim_number():
    device = {"id": "ctrl-a", "phone": ""}
    summary = SIM.phone_attribute_summary(device, _options({"ctrl-a": SIM_A}))
    assert summary == {
        "api_phone_class": "empty",
        "controller_sim_override_active": True,
    }
    assert SIM_A not in repr(summary)

    missing = {"id": "ctrl-b"}
    assert SIM.api_phone_class(missing) == "missing"
    assert SIM.api_phone_class({"phone": None}) == "null"
    assert SIM.api_phone_class({"phone": ""}) == "empty"
    assert SIM.api_phone_class({"phone": " \t"}) == "blank"
    assert SIM.api_phone_class({"phone": SIM_A}) == "non_empty"
    assert SIM.api_phone_class({"phone": 15555550100}) == "unsupported"
    inactive = SIM.phone_attribute_summary(
        {"id": "ctrl-b", "phone": SIM_A}, _options({"ctrl-a": SIM_A})
    )
    assert inactive["controller_sim_override_active"] is False
    assert inactive["api_phone_class"] == "non_empty"
    assert SIM_A not in repr(inactive)


def test_error_text_loses_the_resolved_sim():
    leaked = "POST /devices/1/command HTTP 400: OPN 1;" + SIM_A
    cleaned = SIM.redact_controller_sim(leaked, SIM_A)
    assert cleaned == "POST /devices/1/command HTTP 400: OPN 1;[redacted]"
    assert SIM_A not in cleaned
    assert SIM.redact_controller_sim("no secret here", "") == "no secret here"
    assert SIM.redact_controller_sim(leaked, "   ") == leaked


def test_call_sites_share_the_resolver_and_do_not_log_it():
    button = (GATE / "button.py").read_text(encoding="utf-8")
    init = (GATE / "__init__.py").read_text(encoding="utf-8")
    api = (GATE / "api.py").read_text(encoding="utf-8")
    flow = (GATE / "config_flow.py").read_text(encoding="utf-8")
    sensor = (GATE / "binary_sensor.py").read_text(encoding="utf-8")

    assert "phone_for_command" in button
    assert "phone_for_command" in init
    assert "redact_controller_sim" in button
    assert "redact_controller_sim" in init
    assert 'device.get("phone") or ""' not in button
    assert 'device.get("phone") or ""' not in init
    assert "build_open_command_body" in api
    assert 'f"{int(output_number)};' not in api
    for line in api.splitlines():
        if "_LOGGER" in line:
            assert "_phone" not in line
            assert "device_phone" not in line
    assert "phone_attribute_summary" in button
    assert "phone_attribute_summary" in sensor
    assert '"device_phone"' not in button
    assert '"phone": d.get("phone")' not in sensor

    assert "merge_polling_options" in flow
    assert "apply_controller_sim_change" in flow
    for line in flow.splitlines():
        if "_LOGGER" in line:
            assert "controller_sim" not in line
            assert "SIM_" not in line
