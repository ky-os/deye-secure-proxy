# Worked example — Deye battery-backup config review + consumption audit (read-only)

This reference demonstrates a worked example of a Deye hybrid inverter review. Values are representative and should be replaced with real data from the user's stations.

## Example stations

- **Station A:** station `12345678`, inverter `INV001` (rated 6000 W)
- **Station B:** station `87654321`, inverter `INV002` (rated 5000 W)
- Both `gridInterconnectionType = BATTERY_BACKUP`, work mode `ZERO_EXPORT_TO_LOAD`

> Discover the user's actual stations and devices via `list_stations()` and `list_station_devices()` — never assume hardcoded values.

## Example config read results (Station B inverter)

- `config_system` → `maxSellPower 500, maxSolarPower 3000, zeroExportPower 0, energyPattern LOAD_FIRST, systemWorkMode ZERO_EXPORT_TO_LOAD`
- `config_battery` → `maxChargeCurrent 20, maxDischargeCurrent 50, battLowCapacity 20, battShutDownCapacity 18, battCapacity 52`
- `config_tou` → `touAction on`, six slot times 0100/0500/0900/1300/1700/2100, each `power 5000, voltage 49, soc 20, enableGridCharge false, enableGeneration false`
- `device_latest` live → `BatteryVoltage 53.89, BatteryCurrent -16.52, BatteryPower -890, SOC 100, BatteryRatedCapacity 50`

## The tell that SOC is mis-scaled

Battery reported **SOC 100% at 53.89 V** (≈3.37 V/cell). A 16S LiFePO4 shows ~56.5–58 V when truly full; mid-plateau at ~53 V is really ~60%. The offset between two sites' SOC readings on the SAME LiFePO4 chemistry is direct evidence the voltage curve is not calibrated correctly.

Config `battCapacity 52` vs device-reported `BatteryRatedCapacity 50` — minor mismatch worth noting.

## Consumption audit arithmetic (representative)

Based on ~510 samples at 5-min intervals over ~43 hours:

- Load: mean 281 W, median 182, p90 624, p95 864, max 2038 W
- Daily rates: consumption 6.8, solar-DC 3.9, grid import 3.2, battery discharge 0.7 kWh/day → self-sufficiency ≈ 4.6/6.8 ≈ 57%, gap to zero ≈ 2.9 kWh/day
- Off-sun load (TotalDCInputPower < 50 W): mean 163 W, p90 ~500 W, max ~1171 W
- Battery 52 Ah × 51.2 V × 0.8 ≈ **2.13 kWh usable** → lasts ~13 hr at 163 W avg, ~4.3 hr at 500 W, ~1.8 hr at 1.1 kW peak

Battery alone cannot close a 2.9 kWh/day evening gap.

## API gotchas

- `device_history` granularity != 1 (e.g. 4) with `measurePoints` populated → **error 2101006** "if granularity != 1, measurePoints should be null". Use `device_history` (date granularity) without measurePoints, or `device_history_raw` (timestamp range + measurePoints + page/size) for point-level data.
- Page size 200 returns ~165 KB and auto-spills to `cache/spillover/call_*.txt`. First page alone (200 samples) can be a misleadingly narrow window. Pull ALL pages (`_total_pages/_total_items`) and aggregate the on-disk files with execute_code.
- Corrupted hand-pasted JWT → `auth invalid token`. With the proxy, tokens are managed internally — this error should not occur.

## Net-metering reasoning

Export credits depend on local regulations. In many jurisdictions (e.g., Philippines ERC Resolution 09-2013), export credits are at wholesale/BGC rate, NOT retail — so 1:1 kWh export-vs-import does NOT zero your bill unless enrolled in net metering. Recommended path: skip net metering, drive grid import → 0 kWh via self-consumption + zero export; residual bill is only fixed monthly charges.
