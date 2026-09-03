---
name: deye-inverter-config-review
description: Audit Deye hybrid inverter config for discrepancies.
version: 3.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [deye, deyecloud, solar, inverter, config-review, battery, hybrid]
---

# Deye Inverter Configuration Review

Conduct a read-only audit of Deye hybrid inverter configuration via the **`deye-secure-proxy`** MCP, surface discrepancies between stations and against live telemetry, and recommend adjustments. **Read-only** — never change anything without explicit user confirmation.

## Prerequisites

- `deye-secure-proxy` MCP enabled in `~/.hermes/config.yaml` (the proxy handles auth internally — no credentials needed from the agent)
- Load the `deye-open-mcp` skill for the full tool map and allowed action types

## Procedure

1. `list_stations(page=1, size=20)` → station id, name, capacity, `gridInterconnectionType`, `batterySOC`, `connectionStatus`, `generationPower`
2. `list_station_devices(stationIds=[...])` → device SNs + types. Find the INVERTER per station.
3. For **each inverter**, pull read config in parallel:
   - `get_config_system(deviceSn)` → `systemWorkMode`, `energyPattern`, `maxSellPower`, `maxSolarPower`, `zeroExportPower`
   - `get_config_battery(deviceSn)` → `maxChargeCurrent`, `maxDischargeCurrent`, `battLowCapacity`, `battShutDownCapacity`, `battCapacity`
   - `get_config_tou(deviceSn)` → `touAction`, `timeUseSettingItems[]` (each: `power`, `voltage`, `time` HHMM, `enableGridCharge`, `enableGeneration`, `soc`)
4. Pull live telemetry to cross-check config vs behavior:
   - `get_device_latest(deviceList=[...])` → per-inverter keys: SOC, BatteryPower (neg=charging), TotalGridPower, DailyGridFeedIn, DailyEnergyPurchased, DailyDischargingEnergy, DailyChargingEnergy, BatteryVoltage, RatedPower, BatteryRatedCapacity
   - `get_station_latest(stationId)` → generationPower, consumptionPower, batteryPower, batterySOC, wirePower
5. Build the review table (one row per station), then reconcile for discrepancies.

## Discrepancy checklist

- **Energy-pattern inconsistency between sites:** `LOAD_FIRST` vs `BATTERY_FIRST`. On a residential battery-backup system, `BATTERY_FIRST` should carry the load from battery before grid. Sites using `LOAD_FIRST` will idle a charged battery and buy grid power → highest-leverage fix is aligning to `BATTERY_FIRST`.
- **Grid import with a full battery:** `DailyEnergyPurchased > 0` while SOC ≈ 100% and load small = battery being left idle. Correlate with energy pattern + discharge current limits.
- **Solar production cap:** `maxSolarPower` far below inverter `RatedPower` clips PV on sunny days (e.g. 3000 on a 5000 W unit ≈ 40% headroom). Flag for raise unless intentional.
- **Inert settings:** `maxSellPower` set while `systemWorkMode = ZERO_EXPORT_TO_LOAD` is a no-op. Note only; correct if ever switching to a selling mode.
- **Timezone metadata:** station `regionTimezone` may be misconfigured — harmless if the offset matches, but flag if it could affect TOU scheduling.
- **Battery floors:** sane defaults are `battLowCapacity=20` / `battShutDownCapacity=18` — flag only if inverted (shutdown > low) or extreme.
- **Healthy signs (no action):** zero export holding (`TotalGridPower=0`, `wirePower=0`), surplus PV banking into battery, battery voltage in normal operating range.

## Pitfalls

- **Control/order tools are state-changing** — require explicit per-action user confirmation via the proxy's two-step flow (`propose_control_change` → confirm → `confirm_control_change`). The audit itself is read-only.
- **Token/auth errors** — handled internally by the proxy. If calls fail with auth errors, check `~/.deye/credentials.env` is valid.

## Output style

Summary table first, then numbered discrepancies each with: what's wrong, why it matters (in cost/production terms), and a concrete recommended adjustment. Distinguish genuine problems from inert/no-op settings. Offer to apply fixes explicitly and individually; offer a markdown audit file if the user documents findings in `docs/`.
