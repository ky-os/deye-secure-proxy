---
name: deye-open-mcp
description: Use Deye Open MCP tools to query and operate DeyeCloud stations, devices, telemetry, alarms, configuration, and order/control results through a configured MCP server.
version: 2.0.0
author: Deye Open MCP (proxy adapter)
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [mcp, deyecloud, openapi, solar, inverter, energy-storage]
---

# Deye Open MCP (via Secure Proxy)

> **This skill now operates through `deye-secure-proxy`, a local MCP server.**
> The remote `deye_open` MCP is **disabled** in favor of the local proxy.
> Credentials never leave the proxy process — the agent calls curated tools directly.

## What Changed

- **No credential sourcing.** The agent no longer sources `credentials.env` or calls `get_access_token`.
- **No `call_deye_api`.** The generic HTTP proxy is eliminated — only curated tools are exposed.
- **Two-step control.** State-changing actions require `propose_control_change` → human confirmation → `confirm_control_change`.
- **Device whitelist.** Only known device SNs are accepted for control actions.

## Agent-Visible Tools (via `deye-secure-proxy`)

### Read-only (always safe)

| Tool | Description |
|---|---|
| `list_stations(page, size)` | List all stations |
| `get_station_latest(station_id)` | Live station telemetry |
| `list_station_devices(station_id, page, size)` | Devices under a station |
| `get_device_latest(device_sns)` | Telemetry for up to 10 devices |
| `get_station_alerts(station_id, start_ts, end_ts)` | Station alarm history |
| `get_device_alerts(start_ts, end_ts, device_sn)` | Device alarm history |
| `get_config_system(device_sn)` | Work mode, energy pattern, power caps |
| `get_config_battery(device_sn)` | Battery parameters |
| `get_config_tou(device_sn)` | Time-of-use configuration |
| `get_device_measure_points(device_sn, device_type)` | Available measurement points |
| `get_station_history(station_id, start_at, granularity, end_at)` | Station historical data |
| `get_device_history(device_sn, start_at, granularity, end_at, measure_points)` | Device historical data |

### Control (two-step confirmation required)

| Tool | Description |
|---|---|
| `propose_control_change(device_sn, action_type, params)` | Stage a control action — returns `proposal_id` |
| `confirm_control_change(proposal_id)` | Execute a staged action (one-shot, consumed) |

**Allowed `action_type` values:**
- `set_work_mode` — `{"mode": "SELLING_FIRST"}`
- `set_energy_pattern` — `{"pattern": "BATTERY_FIRST"}`
- `set_solar_sell` — `{"action": "on"}`
- `set_tou_switch` — `{"action": "on", "days": [...6 days...]}`
- `set_tou_update` — `{"items": [...6x TimeUseSettingItem...]}`
- `set_battery_type` — `{"batteryType": "BATT_V"}`
- `set_battery_param` — `{"parameter_type": "MAX_CHARGE_CURRENT", "value": 20}`
- `set_power_limit` — `{"power_type": "MAX_SOLAR_POWER", "value": 5000}`
- `set_limit_control` — `{"function_type": "ZERO_EXPORT_TO_LOAD"}`
- `set_grid_peak_shaving` — `{"action": "on", "power": 3000}`
- `set_battery_mode` — `{"action": "on", "mode_type": "GEN_CHARGE"}`
- `set_smartload` — `{"onGridAlwaysOn": false, ...}`

**Allowed devices:** `2507120169` (BaskSolar1), `2305202443` (BaskSolar2)

## Safety Rules

1. Read-only tools are safe by default — no confirmation needed.
2. For any control action: call `propose_control_change`, present the summary to the user, wait for **explicit** confirmation, then call `confirm_control_change`.
3. Never call control tools based on vague instructions like "optimize it" — ask for exact target + settings.
4. The proxy enforces device whitelisting — attempts to target unknown devices are rejected.
5. Tokens and credentials are managed internally by the proxy — never appear in agent context.

## Troubleshooting

- **"Invalid, expired, or already-used proposal_id"** — Re-propose the action.
- **"Device not in allowed list"** — Only `2507120169` and `2305202443` are whitelisted.
- **Tools unavailable** — Ensure `deye-secure-proxy` is enabled in `~/.hermes/config.yaml` and `deye_open` is disabled.
- **Auth failures** — Check `~/.deye/credentials.env` is valid; the proxy logs to stderr on failure.
