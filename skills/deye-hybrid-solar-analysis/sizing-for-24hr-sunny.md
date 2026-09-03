# Sizing for 24-hour sustain (sunny day) — worked methodology

This reference captures the full calculation so future sessions can reproduce or adapt it without rebuilding from scratch.

## Problem statement

User asked: "What is the minimum battery capacity I need to sustain 24 hours, given sunny weather?"

Interpretation: a sunny day means the PV array covers all daytime loads and recharges the battery. The battery must then carry **all nighttime loads** from sunset until solar ramps again the next morning. The sizing target is nighttime sustain, not daily kWh balance.

## Constants (equatorial, clear day)

| Constant | Value | Notes |
|---|---|---|
| Nighttime window | ~14 hrs | 6 PM – 6 AM, no DST |
| Peak sun hours | ~5 hrs | Good tilt, zero shading, equatorial |
| Inverter + wiring loss | 0.80 | Standard for hybrid solar |
| Safety factor | 1.25× | Aging, temperature, morning/evening ramp |
| Usable DoD | 0.80 | 20% floor; non-comm BMS needs conservative floor |
| 16S LiFePO4 nominal V | 51.2 V | 3.2 V/cell × 16 |

## Appliance load profile (residential, 5 kW inverter)

Built from a typical household. Adjust per the user's actual loads.

| Load | Power | Duty / hrs | Night kWh |
|---|---|---|---|
| Fridge (cycling) | 150 W × 60% | 14 | 1.26 |
| LED lights | 100 W | 6 | 0.60 |
| Fans (bedroom + living) | 150 W | 10 | 1.50 |
| Router / modem | 20 W | 14 | 0.28 |
| Misc (TV, laptop, phone charging) | 200 W | 4 | 0.80 |
| **Total (moderate tier)** | | | **4.44 kWh** |

Tiers for table lookup:
- **Light:** ~3 kWh (fridge + router + minimal lights)
- **Moderate:** ~4.5 kWh (above profile)
- **Heavy:** ~6 kWh (add aircon, water pump, or extended TV/laptop)

## Formula

```
required_usable_kWh = nighttime_load_kWh × 1.25
required_total_kWh   = required_usable_kWh / 0.80
required_Ah          = (required_total_kWh × 1000) / nominal_V
```

## Worked example — 52Ah stock pack

Stock battery: 16S 52Ah LiFePO4 (non-comm BMS).

- Total energy: 51.2 V × 52 Ah = **2.66 kWh**
- Usable (80% DoD): 2.66 × 0.80 = **2.13 kWh**

At the moderate nighttime load (4.44 kWh):
- Required usable: 4.44 × 1.25 = 5.55 kWh
- Required total: 5.55 / 0.80 = 6.94 kWh
- Required Ah: (6.94 × 1000) / 51.2 = **~136 Ah**

**Verdict: stock 52Ah is 62% short for 24hr moderate sustain.**

## Non-comm BMS reality (always flag)

- Inverter estimates SOC from voltage → mis-scales on LiFePO4's flat plateau.
- If app shows ~100% at ~53 V (≈3.3 V/cell), real pack is only **45–65% full**.
- SOC-based low/shutdown floors are NOT real protection.
- ONLY voltage cutoffs protect the cells: charge top ≤58.4 V, low-voltage cut ~46–48 V (16S).
- A undersized pack without BMS comms is at risk of deep discharge — the inverter won't stop at the cell's true cutoff.

## Resilience caveat

This sizing assumes **sunny only** (5 peak sun hours). For cloudy / weather resilience:
- Add 40–60% more capacity.
- Or accept that the battery will not cover 24hr on poor days.

## When real telemetry is available

Replace the assumed nighttime_load_kWh with actual off-sun consumption:
- Off-sun samples = `TotalDCInputPower < 50 W`
- Compute: avg off-sun load × nighttime hours = actual nighttime kWh
- Re-run the formula with the real number.

This yields a personalized sizing instead of the tier lookup.
