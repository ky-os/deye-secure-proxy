---
name: deye-hybrid-solar-analysis
description: Review Deye solar config, battery sizing, and bill-to-zero.
version: 3.0.0
metadata:
  hermes:
    tags: [deye, deyecloud, solar, battery, lifepo4, net-metering, self-consumption]
---

# Deye Hybrid Solar Analysis

Audit and optimize Deye hybrid (battery-backup) solar inverter setups. This skill uses the **`deye-secure-proxy`** MCP — credentials are managed internally, no auth needed from the agent.

## When to load
- "check my deye configuration / review it / any discrepancy"
- "is my battery config right for my [repurposed] battery"
- "how do I zero my electric bill / size the battery / how much wattage to cover my load"
- "audit my consumption" for a Deye station

## Station / Device Discovery

The agent should discover the user's stations and devices dynamically:

1. `list_stations(page=1, size=20)` → get all station IDs and names
2. For each station, `list_station_devices(station_id)` → find inverter SNs
3. Build the station/device map from the response — do NOT hardcode SNs

## CRITICAL SAFETY — "read" tools that actually WRITE

The original Deye MCP has `strategy_dynamic_control_read` / `strategy_dynamic_control_read_result` which are **NOT read-only** — they submit control writes to the live inverter. The proxy **does not expose these tools**, so this risk is eliminated. To READ current config, use:
- `get_config_system(device_sn)` → `maxSellPower, maxSolarPower, zeroExportPower, energyPattern, systemWorkMode`
- `get_config_battery(device_sn)` → `maxChargeCurrent, maxDischargeCurrent, battLowCapacity, battShutDownCapacity, battCapacity`
- `get_config_tou(device_sn)` → `touAction` + `timeUseSettingItems[]`

## Read-only config endpoints

- `get_config_system{deviceSn}` → system work mode, energy pattern, power caps
- `get_config_battery{deviceSn}` → battery currents, capacities, floors
- `get_config_tou{deviceSn}` → TOU action + 6x time intervals
- `get_device_latest{deviceList:[sns]}` → live telemetry (PV, load, grid, battery V/I/P, SOC, temps). Batch up to 10 SNs.
- `get_station_latest{stationId}` → station-level generation, consumption, battery, grid

## Repurposed LiFePO4 battery analysis (non-comm BMS)

No CAN/RS485 BMS communication ⇒ inverter estimates SOC from VOLTAGE, which mis-scales badly on LiFePO4's flat plateau. Reference for common LiFePO4 configurations:

| Configuration | Nominal V | Full/Top V | Empty/Cut V |
|---|---|---|---|
| 16S (48V nominal) | 51.2 | 56.5–58.4 | 44–48 |
| 15S (45V nominal) | 48.0 | 52.5–54.7 | 42.0–45.0 |

- **If the app/API reports ~100% SOC at ~53 V on a 16S pack (≈3.3 V/cell), the pack is really ~45–65% full** — voltage-SOC curve is misconfigured. Consequences: charger stops early (pack chronically ~half-charged), and SOC-based low/shutdown floors are NOT real protection. ONLY the voltage cutoffs (charge top + low-voltage cut) protect the cells.
- Check `get_config_battery` max currents against C-rate: e.g. 20 A charge on 52 Ah = 0.38C (safe); 50 A discharge ≈ 1C (ok).
- When the user says battery-first is "already enabled," trust them but verify `get_config_system.energyPattern` — that field is the source of truth.

## Sizing for 24-hour sustain (sunny day)

**Assumptions (state these to the user — adjust for their location):**
- Nighttime window: ~14 hrs (6 PM – 6 AM) for equatorial regions (no DST)
- Peak sun hours: ~5 hrs on a clear day (good tilt, zero shading)
- Solar production: inverter_rated_W × peak_sun_hours × 0.80 (inverter + wiring loss) ≈ kWh/day
- Nighttime load = battery's sole burden; daytime load covered by solar
- Safety factor: **1.25×** (aging, temperature, ramp)
- Usable DoD: **0.80** (20% floor; non-comm BMS needs conservative floor)

**Formula:**
```
required_usable_kWh = nighttime_load_kWh × 1.25
required_total_kWh   = required_usable_kWh / 0.80
required_Ah          = (required_total_kWh × 1000) / nominal_V
```

**Reference table (51.2V 16S LiFePO4, 5 kW inverter):**

| Nighttime Load | Required Usable | Required Total | Required @51.2V | Verdict on 52Ah stock |
|---|---|---|---|---|
| Light (~3 kWh) | 3.75 kWh | 4.69 kWh | ~92Ah | ❌ 46% short |
| Moderate (~4.5 kWh) | 5.55 kWh | 6.94 kWh | ~136Ah | ❌ 62% short |
| Heavy (~6 kWh) | 7.50 kWh | 9.38 kWh | ~183Ah | ❌ 72% short |

> Non-comm BMS caveat: SOC estimated from voltage mis-scales on LiFePO4's flat plateau. If the app shows 100% at ~53 V (≈3.3 V/cell), real pack is only 45–65% full. ONLY voltage cutoffs protect the cells.

**What to report:**
1. The sizing table (user picks their own load tier)
2. The non-comm BMS warning
3. Caveat: sunny-day only — add 40–60% more for cloudy-day resilience
4. Offer to refine with real telemetry data

## Bill-to-zero / net-metering reality

- "Return to the grid only what we consume" = net metering. Export credits depend on local regulations — many jurisdictions credit at wholesale/avoided-cost rate, NOT retail. 1:1 kWh export-vs-import does NOT zero your bill unless enrolled in a net metering program.
- **Without net metering, the only bill-zeroing lever is self-consumption + zero export**: every kWh consumed from solar/battery avoids the full retail rate. Zero-export + battery-first is the right architecture. Residual bill = fixed monthly (distribution/connection) charges you cannot remove with any inverter.

## Consumption audit → "wattage to zero my bill"

1. Pull raw history: `get_device_history{deviceSn, startAt, granularity, measurePoints:[...], endAt}`. Use `get_device_measure_points` first to confirm available points.
2. **Aggregate with execute_code** — read persisted files off disk; do NOT re-request pages.
3. Compute: avg/median/p90/p95/max load; daily kWh for consumption, solar (DC input), grid import (clip ≥0), battery discharge (clip ≤0); **off-sun load = consumption samples where TotalDCInputPower < 50 W**.
4. Sizing: usable battery kWh ≈ Ah × usable SOC fraction × nominal V. Compare against off-sun load and daily gap.
5. Caveat: a just-live station (<2 days of data) gives a PRELIMINARY profile — offer to pull more days before locking recommendations.

## Control Actions

To change any inverter setting, use the proxy's two-step flow:
1. `propose_control_change(device_sn, action_type, params)` → returns `proposal_id` + summary
2. Present summary to user, wait for explicit confirmation
3. `confirm_control_change(proposal_id)` → executes (one-shot)

See the `deye-open-mcp` skill for the full list of `action_type` values.
