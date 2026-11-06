# Eldes Gate — Home Assistant Integration

Unofficial Home Assistant integration for [Eldes](https://eldesalarms.com/)
GSM gate / garage-door controllers, talking to the same cloud backend
(`ea-gates-api.e-alarms.com`) the official **Eldes Gates** Android app uses.

> Reverse-engineered from the v2.1.2-prod APK. Not affiliated with or
> endorsed by Eldes.

## Features

- **Per-output Open button** – one `button.*` entity per controller output,
  pressing it sends a `POST /devices/{id}/command` and polls the cloud
  for delivery confirmation.
- **Connectivity binary sensor** – `binary_sensor.<gate>_online` reflects
  the controller's `is_alive` flag (cloud-side liveness, not gate
  position — see notes).
- **Diagnostic sensors** – status code, last-updated timestamp, model id.
- **Redacted diagnostics download** – Home Assistant's standard
  **Download diagnostics** action summarizes the device list already in
  memory. It reports whether `phone` is missing, null, empty, blank, or
  non-empty, and whether another allowlisted field exists. Values,
  names, identifiers, and unknown JSON keys are left out. It does not
  call Eldes and does not send a gate command. See
  [Privacy-preserving diagnostics](#privacy-preserving-diagnostics).
- **Experimental per-controller SIM override** – optional number stored
  in the integration options and used as the controller SIM in the
  existing `output;SIM` open command. It is not the account username.
  If it is unset, the device-list `phone` field is used as before,
  including when that field is blank. This does not guarantee the gate
  will move. See
  [Controller SIM override](#controller-sim-override-experimental).
- **Account-level buttons** – per config entry, on a synthetic "Eldes
  Account" device:
  - `button.eldes_account_<phone>_send_password_reset_email` – fires
    `POST /auth/forgot-password` against the account's own email.
  - `button.eldes_account_<phone>_refresh_devices` – forces a refresh.
- **Services**:
  - `eldes_gate.open` – send an open command from automations / scripts.
  - `eldes_gate.refresh` – force a re-poll of the device list.
  - `eldes_gate.forgot_password` – trigger a password-reset email
    (unauthenticated `POST /auth/forgot-password`).
- **Forgot-password from setup / re-auth** – the config flow's entry
  screen offers "Forgot password? Send a reset email" as a menu option,
  so you don't need to be logged in or know the service name to trigger
  a reset. Same option appears in the re-auth flow.
- **Re-auth flow** – if the server rejects the cached credentials, HA
  prompts you for a new password instead of silently failing.
- **Options flow** – tune the polling interval (default 5 min) and the
  open-command confirmation timeout (default 20 s).

## Requirements

- Home Assistant 2024.1.0 or later
- An Eldes Gates account (phone number + password) already provisioned on
  the controller

## Installation

### HACS (recommended)

1. In HACS → Integrations → ⋮ → **Custom repositories**, add
   `https://github.com/bogdan-calapod/ha-eldes-gate` as **Integration**.
2. Install **Eldes Gate** from HACS.
3. Restart Home Assistant.
4. **Settings → Devices & services → Add integration → Eldes Gate**.

### Manual

1. Copy `custom_components/eldes_gate/` into your HA `config/custom_components/`.
2. Restart Home Assistant.
3. Add the integration through the UI as above.

## Entity layout

For each Eldes device the integration registers an HA **device** with:

| Entity | Type | Notes |
|---|---|---|
| `binary_sensor.<gate>_online` | connectivity | `is_alive` from `GET /devices` |
| `sensor.<gate>_status` | diagnostic | numeric status code |
| `sensor.<gate>_last_updated` | diagnostic (timestamp) | server-reported `updated_at` |
| `sensor.<gate>_model_id` | diagnostic | controller model id |
| `button.<gate>_open_<output_name>` | button | one per output; press to open |

Output buttons take their friendly names from `control_name`, falling
back to `zone_name`, then `Output <n>`.

## Service example

```yaml
service: eldes_gate.open
data:
  device: "Main"       # device id or name
  output: 1            # output number, control_name, or zone_name
  wait: true           # default; set false to fire-and-forget
  timeout: 20          # optional override of the entry option
```

## Dashboards

Once the integration is added, every gate appears as an HA **device** with
its own buttons, sensors and connectivity binary sensor. You can drop any
of them on a dashboard with the regular UI editor (**Edit dashboard →
Add card → pick an entity**). A few patterns that work well:

### Tile card per gate (recommended)

```yaml
type: tile
entity: button.bariera_c8_open       # single-output device
name: Bariera C8
icon: mdi:boom-gate
tap_action:
  action: perform-action
  perform_action: button.press
  target:
    entity_id: button.bariera_c8_open
```

For a multi-output device (one button per output):

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: binary_sensor.poarta_pietonala_c8_online
    name: Poarta Pietonala C8
    icon: mdi:gate
  - type: horizontal-stack
    cards:
      - type: tile
        entity: button.poarta_pietonala_c8_open_poarta_c8
        name: Pedestrian
        icon: mdi:walk
        tap_action: { action: perform-action, perform_action: button.press,
                      target: { entity_id: button.poarta_pietonala_c8_open_poarta_c8 } }
```

### Classic button card

```yaml
type: button
entity: button.bariera_c8_open
name: Open Barrier
icon: mdi:boom-gate-up
show_state: false
tap_action:
  action: perform-action
  perform_action: button.press
  target:
    entity_id: button.bariera_c8_open
```

### Entities card grouping a device

```yaml
type: entities
title: Bariera C8
entities:
  - entity: binary_sensor.bariera_c8_online
  - entity: sensor.bariera_c8_status
  - entity: sensor.bariera_c8_last_updated
  - type: button
    name: Open
    icon: mdi:boom-gate-up
    action_name: OPEN
    tap_action:
      action: perform-action
      perform_action: button.press
      target:
        entity_id: button.bariera_c8_open
```

### Calling the service directly (scripts / automations / shortcuts)

```yaml
script:
  open_bariera_c8:
    alias: Open Bariera C8
    sequence:
      - service: eldes_gate.open
        data:
          device: "Bariera C8"
          output: 1
          wait: true
          timeout: 20
```

This is also what you'd point the iOS / Android Home Assistant
companion-app widgets at if you want a one-tap open shortcut on your
phone home screen.

### Entity naming convention

With `has_entity_name=True`, HA prefixes the device name automatically.
So a controller named "Bariera C8" with a single output gives you:

| Entity ID | Friendly name |
|---|---|
| `button.bariera_c8_open` | Bariera C8 Open |
| `binary_sensor.bariera_c8_online` | Bariera C8 Online |
| `sensor.bariera_c8_status` | Bariera C8 Status |
| `sensor.bariera_c8_last_updated` | Bariera C8 Last updated |
| `sensor.bariera_c8_model_id` | Bariera C8 Model ID |

Controllers with multiple outputs get one `button.*_open_<output>` per
output, e.g. `button.<gate>_open_pedestrian`, `button.<gate>_open_vehicle`.

Status / Last updated / Model ID are tagged as **diagnostic** entities,
so they sit under the "Diagnostic" section of the device page (still
addable to dashboards if you want them there).

## How it works under the hood

Endpoints exercised (all on `https://ea-gates-api.e-alarms.com`):

| Method | Path | Used for |
|---|---|---|
| `POST` | `/auth/login` | Sign in. Body `{username, password, uuid}`, header `X-App-Version-Code`. Returns `{access_token, expires_at, email}`. |
| `POST` | `/auth/logout` | Drop the session token. |
| `POST` | `/auth/forgot-password` | Request a password-reset email. Body `{email}`. Unauthenticated. |
| `GET`  | `/devices` | Pull every device with its outputs. |
| `POST` | `/devices/{id}/command` | Open: body `{"variables":{"OPN":"<output>;<device_phone>"}}` → `{SEQ, state}`. |
| `GET`  | `/devices/{id}/command/{seq}` | Poll for delivery confirmation. |

The `OPN` value format (`<output_number>;<device_phone>`) was extracted
from the smali of `GatesRepositoryImpl.sendOpen` (`StringBuilder().append(controllerNr).append(';').append(devicePhone)`).
`device_phone` is the SIM phone number on the controller (`DeviceDetail.phone`),
**not** the user's account phone. The string format is a leftover from
the original SMS-based Eldes protocol.

The HTTP client sets `User-Agent: okhttp/4.12.0` because the backend is
fronted by Cloudflare, which blocks generic Python clients with
"error code: 1010" (browser fingerprint). The official app uses OkHttp,
so we match it.

## Single-device UUID lock (important)

The Eldes cloud API enforces **one device UUID per account at a time**:

```
empty UUID      → 400 "username, password and uuid are required"
new UUID        → 401 "this account registered on a different device"
the bound UUID  → 200 OK
```

The official mobile app sidesteps this by generating one UUID on first
install (stored as `vendorid` in its `SharedPreferences`) and reusing
it forever. As soon as a second client logs in with a different UUID,
the server rebinds and the previous client gets the 401 on its next
attempt.

For HA this means **two realistic setups**:

1. **HA-only.** Leave the "Device UUID" field in the config flow empty.
   The integration mints a fresh UUID and binds the account to itself.
   The phone app will sign out the next time it tries to talk to the
   server. (You can still re-log in on the phone later, but that will
   then kick HA out — tug-of-war.)
2. **HA + phone sharing the same UUID.** Paste the phone's `vendorid`
   into the "Device UUID" field. Both clients then look identical to
   the server's UUID check, so neither kicks the other on login. They
   each still get their own bearer token.

### Extracting the phone's UUID

On a **rooted Android** device:

```sh
adb shell su -c \
  'cat /data/data/lt.eldes.smartgate.appswidget/shared_prefs/lt.eldes.smargate.appswidget.xml' \
  | grep vendorid
```

> Note the SharedPreferences filename has a typo — `smargate`, not
> `smartgate`. It's a quirk in the app itself.

You'll get a line like:

```xml
<string name="vendorid">a1b2c3d4-e5f6-7890-abcd-ef1234567890</string>
```

Paste that UUID into the integration's setup form.

On a **non-rooted** device the cleanest path is `adb backup` of the
package, unpacking the tar inside, and grepping the same file. Some
Android versions disable backup for this app — in that case there's no
non-root way to extract it and you're stuck with option 1.

## Caveats

- **No real gate position**. The API tells you the command was
  *delivered* (`confirmed:true`), not whether the physical gate moved.
  This is why outputs are exposed as `button` entities rather than
  `cover` entities.
- **No TLS pinning**. The official app doesn't pin either; we trust the
  system CA store.
- **Account-enumeration in `/auth/forgot-password`**. The server returns
  HTTP 404 `"email not found or not verified"` for unknown addresses
  and a 2xx for known ones. Surfaced as `EldesAPIError` upstream.
- **Cloud-only**. There's no local LAN protocol exposed; every entity
  state depends on cloud polling.

## Privacy-preserving diagnostics

Version 0.3.0 includes Home Assistant's standard diagnostics download. Use it
to see the shape of the device list the integration already stored
(including whether `phone` is absent or another known field is present)
without printing phone numbers, names, identifiers, credentials, or tokens.
`controller_sim_override_count` is only a count of saved SIM overrides;
the digits are not in the file.

The download does not refresh, does not call the Eldes API, and does not
send an open command. Gate behaviour is unchanged. A missing candidate
means that exact key was not in the stored list; it does not describe the
controller's own output settings.

### Install this version

Install the **whole** `custom_components/eldes_gate/` directory from this
revision. Copying only `diagnostics.py` and `diagnostics_data.py` leaves
`manifest.json` at 0.2.0 and omits the options code, so the installation
does not match the version you are running.

1. Replace `config/custom_components/eldes_gate/` with the full directory
   from this revision.
2. Confirm `manifest.json` contains `"version": "0.3.0"` before you restart.
3. Restart Home Assistant.
4. Confirm the existing Eldes Gate entry is still there. Do not press
   **Open** and do not run `eldes_gate.open` merely to test the install.

No Eldes account, UUID, or gate setting is changed by installing or by
downloading the report. Saving a controller SIM override (below) only
writes an integration option; it does not send a command.

### Download the report

Integration page (every controller, preferred when a file might be shared):

1. **Settings → Devices & services**.
2. Open **Eldes Gate**.
3. Open the three-dot menu and choose **Download diagnostics**.

One gate, from that gate's device page (not the synthetic Eldes Account
device):

1. **Settings → Devices & services**.
2. Open **Eldes Gate**, then open the gate device.
3. Open the three-dot menu and choose **Download diagnostics**.

Home Assistant names a device download using the device's display name.
The Eldes Account device name contains the login phone, so do not download
diagnostics from that device if the file will leave the machine. The JSON
body this integration adds still omits that phone. The account-device
download also contains no controller summary; use the integration menu or
the gate device instead.

### How to read `data` in the JSON file

In `data.devices[]`:

| Field | Meaning |
|---|---|
| `phone.class` | The key the open command reads. `missing` (no key), `null`, `empty` (`""`), `blank` (whitespace only), or `non_empty`. |
| `phone.type` / `char_length` / `digit_count` | Type and sizes only. The characters are not included. |
| `alternate_allowlisted_phone_field_present` | Some other name from the fixed candidate list (`device_phone`, `msisdn`, `sim`, …) is present on the device, on an output, or one level inside a candidate value. |
| `possible_unlisted_phone_field` | Some key outside that list has a phone-like name, a digit-like name, or a phone-shaped value. The name and the value are omitted. |
| `safe_fields` | Only `is_alive` when it is a bool, and `model_id` / `status` when they are small integers. |
| `outputs.items[].number` | Output number when it is a small integer. Labels such as `control_name` are lengths only. |

`data.options` includes only the polling interval and the confirmation
timeout. The config-entry phone, password, and UUID are not read.

Home Assistant wraps this payload with its own `home_assistant`,
`custom_components`, and `integration_manifest` sections. Review the whole
file before sharing it. Those sections are outside this redaction.

### Roll back

1. Restore the previous full `config/custom_components/eldes_gate/`
   directory (a 0.2.0 tree has no `diagnostics.py` and no SIM option).
2. Restart Home Assistant.

The **Download diagnostics** action for Eldes Gate disappears, and the
options menu no longer offers a controller SIM. An override already saved
in Home Assistant's config entry is ignored by the older code. To drop
that stored value, remove it in the 0.3.0 options screen before rolling
back. Nothing on the Eldes account or the gate was changed.

## Controller SIM override (experimental)

The open command is still `output_number;controller_sim`. Output numbers
are not remapped. The phone on the Eldes sign-in form is the **account
username** and is not used in that command.

The device-list field `phone` is what the command uses when no override
is saved. If that field is missing, null, or `""`, the command is sent
with a blank phone (`1;` for output 1). That is the same behavior as
before this option existed. A saved override replaces only that blank
(or any other list value) for the controller you pick. It is an
experiment. A non-blank value here does **not** mean the gate will move.

The button and the `eldes_gate.open` service use the same resolution.
Entity attributes show `api_phone_class` (`missing`, `null`, `empty`,
`blank`, `non_empty`, or `unsupported`) and
`controller_sim_override_active` (`true`/`false`). They do not show the
digits. Diagnostics do not show them either. The integration does not
write the number into its log lines or error text. Home Assistant does
store the option in the config entry so the command can use it; do not
paste a debug trace of the options form if that trace contains the field.

Accepted form: 8 to 15 ASCII digits, with an optional leading `+`.
The integration does not add a country prefix. Spaces, dashes,
parentheses, letters, and `;` are rejected so the value cannot add
another field to the command.

### Set or remove it

1. **Settings → Devices & services → Eldes Gate → Configure** (gear icon).
2. Choose **Controller SIM number (experimental)**.
3. Choose the controller by its name. The list does not include the SIM.
4. Enter the controller SIM, or leave the field empty / enable
   **Remove saved SIM number**, then submit.
5. Do not press **Open** unless you intend to try the command.

Polling interval and confirmation timeout are the other menu item.
Changing them keeps any saved SIM overrides. Saving a SIM keeps the
polling settings and any other controller's override.

`api_phone_state` on that form is the device-list field, not the saved
override. `empty` means the list value is `""`.

### Offline test

```sh
python -m pytest tests
```

The tests load the pure modules without Home Assistant and without
network. Diagnostics checks use synthetic secrets. SIM checks use
obviously fake numbers and cover precedence, per-controller isolation,
option preservation and removal, invalid input, privacy, and the
open-command body.

## Development

Reverse-engineering source files (apktool/jadx output, not in this repo):

- `ApiService.java` – Retrofit interface
- `g8/e.java` – Hilt module with the base URL + OkHttp config
- `GatesRepositoryImpl.smali` ~12055–12087 – exact OPN string format
- `LoginResponse.java`, `DeviceDetail.java`, `CommandStatusResponse.java`,
  `DeviceCommandResponse.java`, `ForgotPasswordRequest.java` – JSON shapes

## License

MIT. See [LICENSE](LICENSE).
