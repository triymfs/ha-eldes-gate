"""Config flow for the Eldes Gate integration."""

from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import EldesAPI, EldesAPIError, EldesAuthError
from .const import (
    ATTR_EMAIL,
    CONF_CONTROLLER_SIM_OVERRIDES,
    CONF_OPEN_TIMEOUT,
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_UPDATE_INTERVAL,
    CONF_UUID,
    DEFAULT_OPEN_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_OPEN_TIMEOUT,
    MAX_UPDATE_INTERVAL,
    MIN_OPEN_TIMEOUT,
    MIN_UPDATE_INTERVAL,
)
from .sim_override import (
    SimOverrideError,
    apply_controller_sim_change,
    copy_options,
    lookup_controller_sim,
    merge_polling_options,
    phone_attribute_summary,
)

_LOGGER = logging.getLogger(__name__)


async def _validate_credentials(
    hass: HomeAssistant, phone: str, password: str, uuid_value: str
) -> str | None:
    """Try to log in. Return None on success or an error key string."""
    api = EldesAPI(phone, password, uuid_value)
    try:
        await hass.async_add_executor_job(api.validate)
    except EldesAuthError:
        return "invalid_auth"
    except EldesAPIError:
        return "cannot_connect"
    except Exception:  # pragma: no cover
        _LOGGER.exception("Unexpected error validating Eldes credentials")
        return "unknown"
    finally:
        await hass.async_add_executor_job(api.close)
    return None


async def _send_forgot_password(hass: HomeAssistant, email: str) -> str | None:
    """POST /auth/forgot-password.

    Returns None on success or an error key on failure. The endpoint is
    unauthenticated, so we instantiate EldesAPI with empty creds — only
    the HTTP session is used.
    """
    api = EldesAPI("", "", "")
    try:
        await hass.async_add_executor_job(api.forgot_password, email)
    except EldesAPIError as err:
        # Server distinguishes "email not found or not verified" (404)
        # from generic errors. Surface both, but tell them apart so the
        # UI can render a helpful hint.
        msg = str(err).lower()
        if "not found" in msg or "not verified" in msg or "404" in msg:
            return "email_not_found"
        _LOGGER.warning("forgot_password failed: %s", err)
        return "cannot_connect"
    except Exception:  # pragma: no cover
        _LOGGER.exception("Unexpected error sending forgot-password")
        return "unknown"
    finally:
        await hass.async_add_executor_job(api.close)
    return None


class EldesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Initial setup flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Entry point: pick between signing in and requesting a reset email."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["sign_in", "forgot_password"],
        )

    async def async_step_sign_in(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """The actual credentials form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = user_input[CONF_PHONE].strip()
            password = user_input[CONF_PASSWORD]
            # The Eldes API enforces a single-bound-UUID policy per account:
            # every fresh login from a different UUID gets back 401
            # "this account registered on a different device".
            #
            # By default we mint a new UUID. The user can paste the phone
            # app's UUID instead to coexist with the mobile app (both look
            # like the same device to the server). See README for how to
            # extract `vendorid` from the app's SharedPreferences.
            raw_uuid = (user_input.get(CONF_UUID) or "").strip()
            uuid_value = raw_uuid or str(uuid_mod.uuid4())

            await self.async_set_unique_id(phone.lower())
            self._abort_if_unique_id_configured()

            error = await _validate_credentials(
                self.hass, phone, password, uuid_value
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"Eldes ({phone})",
                    data={
                        CONF_PHONE: phone,
                        CONF_PASSWORD: password,
                        CONF_UUID: uuid_value,
                    },
                    options={
                        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                        CONF_OPEN_TIMEOUT: DEFAULT_OPEN_TIMEOUT,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_PHONE): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_UUID, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="sign_in",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "uuid_hint": (
                    "Leave blank to mint a new device UUID (will kick the "
                    "Eldes mobile app off this account the next time it "
                    "re-logs in). Paste the phone's UUID to share the slot."
                ),
            },
        )

    async def async_step_forgot_password(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Trigger POST /auth/forgot-password from the setup screen."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = (user_input.get(ATTR_EMAIL) or "").strip()
            if "@" not in email:
                errors["base"] = "invalid_email"
            else:
                error = await _send_forgot_password(self.hass, email)
                if error:
                    errors["base"] = error
                else:
                    return self.async_abort(
                        reason="forgot_password_sent",
                        description_placeholders={"email": email},
                    )

        return self.async_show_form(
            step_id="forgot_password",
            data_schema=vol.Schema({vol.Required(ATTR_EMAIL): str}),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Triggered by the API client when credentials are no longer valid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """During reauth, offer either to re-enter the password or send a
        reset email."""
        # If the user typed something it's the password form; otherwise
        # show a menu first.
        if user_input is None:
            return self.async_show_menu(
                step_id="reauth_confirm",
                menu_options=["reauth_password", "forgot_password"],
            )
        # Fall through is unused (each menu choice routes to its own step).
        return await self.async_step_reauth_password(user_input)

    async def async_step_reauth_password(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry_id = self.context.get("entry_id")
        entry = (
            self.hass.config_entries.async_get_entry(entry_id)
            if entry_id
            else None
        )

        if user_input is not None and entry is not None:
            password = user_input[CONF_PASSWORD]
            error = await _validate_credentials(
                self.hass,
                entry.data[CONF_PHONE],
                password,
                entry.data[CONF_UUID],
            )
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_password",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EldesOptionsFlow:
        # The base class auto-injects `config_entry` on the returned
        # OptionsFlow instance; passing it here would set the read-only
        # property and 500 the UI on HA 2024.12+.
        return EldesOptionsFlow()


def _loaded_controllers(hass: HomeAssistant, entry: config_entries.ConfigEntry) -> list[dict[str, Any]]:
    """Controllers from the last in-memory device list. No API call."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    data = getattr(coordinator, "data", None)
    devices = getattr(data, "devices", None)
    if not isinstance(devices, list):
        return []
    return [
        device
        for device in devices
        if isinstance(device, dict) and device.get("id") is not None
    ]


def _controller_choices(devices: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Dropdown labels. The SIM number is never included."""
    choices: list[dict[str, str]] = []
    used: set[str] = set()
    for index, device in enumerate(devices):
        name = device.get("name")
        if isinstance(name, str) and name.strip():
            label = name.strip()
        else:
            label = f"Controller {index + 1}"
        if label in used:
            label = f"{label} ({index + 1})"
        used.add(label)
        choices.append({"value": str(device["id"]), "label": label})
    return choices


class EldesOptionsFlow(config_entries.OptionsFlow):
    """Polling settings and an optional per-controller SIM override.

    Note: do NOT define __init__ here. Recent HA versions (2024.12+)
    expose `config_entry` as a read-only property on OptionsFlow that
    the framework auto-injects; assigning to it raises
    `AttributeError: property 'config_entry' of '...' object has no setter`
    and the UI surfaces it as a 500 when the user opens the gear icon.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["polling", "controller_sim"],
        )

    async def async_step_polling(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            # Only interval keys are taken from the form. Saved SIM
            # overrides stay on the entry and are not logged.
            return self.async_create_entry(
                title="",
                data=merge_polling_options(self.config_entry.options, user_input),
            )

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        current_timeout = self.config_entry.options.get(
            CONF_OPEN_TIMEOUT, DEFAULT_OPEN_TIMEOUT
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=current_interval
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                ),
                vol.Optional(
                    CONF_OPEN_TIMEOUT, default=current_timeout
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_OPEN_TIMEOUT, max=MAX_OPEN_TIMEOUT),
                ),
            }
        )
        return self.async_show_form(step_id="polling", data_schema=schema)

    async def async_step_controller_sim(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        devices = _loaded_controllers(self.hass, self.config_entry)
        if not devices:
            return self.async_abort(reason="no_controllers_loaded")
        if user_input is not None:
            self._controller_sim_device_id = str(user_input["controller"])
            return await self.async_step_controller_sim_edit()

        schema = vol.Schema(
            {
                vol.Required("controller"): SelectSelector(
                    SelectSelectorConfig(
                        options=_controller_choices(devices),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="controller_sim",
            data_schema=schema,
        )

    async def async_step_controller_sim_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        device_id = getattr(self, "_controller_sim_device_id", None)
        devices = _loaded_controllers(self.hass, self.config_entry)
        device = next(
            (
                item
                for item in devices
                if device_id is not None and str(item.get("id")) == device_id
            ),
            None,
        )
        if device is None:
            return self.async_abort(reason="controller_not_in_list")

        summary = phone_attribute_summary(device, self.config_entry.options)
        errors: dict[str, str] = {}
        if user_input is not None:
            # A missing text field must not wipe a saved number. An explicit
            # empty field or the removal checkbox removes only this controller.
            clear = bool(user_input.get("clear_controller_sim"))
            field_present = "controller_sim_phone" in user_input
            raw_phone = user_input.get("controller_sim_phone")
            blank = isinstance(raw_phone, str) and raw_phone.strip() == ""
            if not clear and not field_present:
                return self.async_create_entry(
                    title="",
                    data=copy_options(self.config_entry.options),
                )
            try:
                updated = apply_controller_sim_change(
                    self.config_entry.options,
                    device_id,
                    raw_phone,
                    clear=clear or blank,
                )
            except SimOverrideError:
                errors["base"] = "invalid_controller_sim"
            else:
                return self.async_create_entry(title="", data=updated)

        overrides = self.config_entry.options.get(CONF_CONTROLLER_SIM_OVERRIDES)
        saved = lookup_controller_sim(overrides, device_id)
        schema = vol.Schema(
            {
                vol.Optional(
                    "controller_sim_phone",
                    description={"suggested_value": saved or ""},
                ): str,
                vol.Optional("clear_controller_sim", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="controller_sim_edit",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "api_phone_state": summary["api_phone_class"],
                "override_active": (
                    "yes" if summary["controller_sim_override_active"] else "no"
                ),
            },
        )
