#!/usr/bin/env python3
"""
Deye Secure Proxy MCP — local stdio MCP server.
Reads credentials from ~/.deye/credentials.env, caches tokens securely,
and exposes ONLY curated read + two-step control tools.
The LLM agent never sees app_secret, password, or access_token.
"""
import os
import sys
import json
import time
import hashlib
import asyncio
import uuid
import logging
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# STDERR-only logging (stdio transport: stdout is JSON-RPC)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("deye-proxy")

# ---------------------------------------------------------------------------
# Paths & credential loading
# ---------------------------------------------------------------------------
DEYE_DIR = Path.home() / ".deye"
CREDS_FILE = DEYE_DIR / "credentials.env"
TOKEN_CACHE = DEYE_DIR / ".token_cache.json"
PROPOSALS_FILE = DEYE_DIR / ".pending_proposals.json"
BASE_URL = "https://eu1-developer.deyecloud.com"

# Allowed devices (station_id, device_sn) — fill from your known hardware
ALLOWED_STATIONS = {61688124, 62558309}
ALLOWED_DEVICES = {"2507120169", "2305202443"}


def _load_env(path: Path) -> dict:
    d = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            d[k.strip()] = v
    return d


_creds = _load_env(CREDS_FILE)
APP_ID = _creds["DEYE_APP_ID"]
APP_SECRET = _creds["DEYE_APP_SECRET"]
EMAIL = _creds["DEYE_EMAIL"]
PASSWORD = _creds["DEYE_PASSWORD"]
DC = _creds.get("DEYE_DATA_CENTER", "eu")

log.info("Credentials loaded. APP_ID=%s DC=%s", APP_ID, DC)

# ---------------------------------------------------------------------------
# Token manager (memory + disk cache, chmod 600)
# ---------------------------------------------------------------------------
_token: Optional[str] = None
_token_expires: float = 0.0


async def get_token(httpx_client) -> str:
    global _token, _token_expires
    now = time.time()

    # In-memory cache
    if _token and now < _token_expires - 300:
        return _token

    # Disk cache
    if TOKEN_CACHE.exists():
        try:
            data = json.loads(TOKEN_CACHE.read_text())
            if now < data["expires_at"] - 300:
                _token = data["token"]
                _token_expires = data["expires_at"]
                log.info("Token loaded from disk cache.")
                return _token
        except Exception:
            pass

    # Fetch new — SHA256 the password per Deye convention
    pw_hash = hashlib.sha256(PASSWORD.encode()).hexdigest()
    log.info("Requesting new Deye access token...")

    resp = await httpx_client.post(
        f"{BASE_URL}/v1.0/account/token?appId={APP_ID}",
        json={
            "appSecret": APP_SECRET,
            "email": EMAIL,
            "password": pw_hash,
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()

    if not body.get("success"):
        raise RuntimeError(f"Deye auth failed: {body.get('msg')}")

    _token = body["accessToken"]
    _token_expires = time.time() + int(body.get("expiresIn", 86400))

    TOKEN_CACHE.write_text(
        json.dumps({"token": _token, "expires_at": _token_expires})
    )
    os.chmod(TOKEN_CACHE, 0o600)
    log.info("Token refreshed, expires_in=%ds", int(body.get("expiresIn", 0)))
    return _token


async def deye_post(httpx_client, path: str, body: dict) -> dict:
    token = await get_token(httpx_client)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = await httpx_client.post(
        f"{BASE_URL}{path}", json=body, headers=headers, timeout=60
    )
    if resp.status_code == 401:
        # Token expired — force refresh and retry once
        global _token
        _token = None
        token = await get_token(httpx_client)
        headers["Authorization"] = f"Bearer {token}"
        resp = await httpx_client.post(
            f"{BASE_URL}{path}", json=body, headers=headers, timeout=60
        )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Proposal store (two-step confirmation for control actions)
# ---------------------------------------------------------------------------
def _load_proposals() -> dict:
    if not PROPOSALS_FILE.exists():
        return {}
    try:
        return json.loads(PROPOSALS_FILE.read_text())
    except Exception:
        return {}


def _save_proposals(p: dict):
    PROPOSALS_FILE.write_text(json.dumps(p))
    os.chmod(PROPOSALS_FILE, 0o600)


# Map friendly action_type -> (rest_path, payload_builder)
ACTION_MAP = {
    "set_work_mode": (
        "/v1.0/order/sys/workMode/update",
        lambda sn, p: {"deviceSn": sn, "workMode": p["mode"]},
    ),
    "set_energy_pattern": (
        "/v1.0/order/sys/energyPattern/update",
        lambda sn, p: {"deviceSn": sn, "energyPattern": p["pattern"]},
    ),
    "set_solar_sell": (
        "/v1.0/order/sys/solarSell/control",
        lambda sn, p: {"deviceSn": sn, "action": p["action"]},
    ),
    "set_tou_switch": (
        "/v1.0/order/sys/tou/switch",
        lambda sn, p: {"deviceSn": sn, "action": p["action"], "days": p.get("days", [])},
    ),
    "set_tou_update": (
        "/v1.0/order/sys/tou/update",
        lambda sn, p: {"deviceSn": sn, "timeUseSettingItems": p["items"]},
    ),
    "set_battery_type": (
        "/v1.0/order/battery/type/update",
        lambda sn, p: {"deviceSn": sn, "batteryType": p["battery_type"]},
    ),
    "set_battery_param": (
        "/v1.0/order/battery/parameter/update",
        lambda sn, p: {
            "deviceSn": sn,
            "paramterType": p["parameter_type"],
            "value": p["value"],
        },
    ),
    "set_power_limit": (
        "/v1.0/order/sys/power/update",
        lambda sn, p: {
            "deviceSn": sn,
            "powerType": p["power_type"],
            "value": p["value"],
        },
    ),
    "set_limit_control": (
        "/v1.0/order/sys/limitControl",
        lambda sn, p: {"deviceSn": sn, "limitControlFunctionType": p["function_type"]},
    ),
    "set_grid_peak_shaving": (
        "/v1.0/order/gridPeakShaving/control",
        lambda sn, p: {"deviceSn": sn, "action": p["action"], "power": p.get("power", 0)},
    ),
    "set_battery_mode": (
        "/v1.0/order/battery/modeControl",
        lambda sn, p: {
            "deviceSn": sn,
            "action": p["action"],
            "batteryModeType": p["mode_type"],
        },
    ),
    "set_smartload": (
        "/v1.0/order/smartload/update",
        lambda sn, p: {"deviceSn": sn, **{k: v for k, v in p.items() if k != "deviceSn"}},
    ),
}

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
try:
    from mcp.server.fastmcp import FastMCP
    import httpx
except ImportError as e:
    log.error(
        "Missing deps. Install with: pip install mcp httpx  (or uv add mcp httpx)"
    )
    sys.exit(1)

mcp = FastMCP("deye-secure-proxy")


# ─── READ-ONLY TOOLS (always safe) ─────────────────────────────────────────


@mcp.tool()
async def list_stations(page: int = 1, size: int = 20) -> str:
    """List all Deye stations under the account. Read-only."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(c, "/v1.0/station/list", {"page": page, "size": size})
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_station_latest(station_id: int) -> str:
    """Get latest real-time data for a station (power, battery SOC, grid)."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(
            c, "/v1.0/station/latest", {"stationId": station_id}
        )
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def list_station_devices(
    station_id: int, page: int = 1, size: int = 20
) -> str:
    """List inverters and collectors under a station."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(
            c,
            "/v1.0/station/device",
            {"stationIds": [station_id], "page": page, "size": size},
        )
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_device_latest(device_sns: list[str]) -> str:
    """Get latest telemetry for up to 10 devices by SN."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(
            c, "/v1.0/device/latest", {"deviceList": device_sns}
        )
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_station_alerts(
    station_id: int, start_timestamp: int, end_timestamp: int
) -> str:
    """Get alarm/alert history for a station. Timestamps are Unix epoch seconds."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(
            c,
            "/v1.0/station/alertList",
            {
                "stationId": station_id,
                "startTimestamp": start_timestamp,
                "endTimestamp": end_timestamp,
                "page": 1,
                "size": 50,
            },
        )
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_device_alerts(
    start_timestamp: int,
    end_timestamp: int,
    device_sn: str = "",
) -> str:
    """Get device alerts. Optionally filter by device_sn."""
    body = {
        "startTimestamp": start_timestamp,
        "endTimestamp": end_timestamp,
        "page": 1,
        "size": 20,
    }
    if device_sn:
        body["deviceSn"] = device_sn
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(c, "/v1.0/device/alertList", body)
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_config_system(device_sn: str) -> str:
    """Read system work mode and power cap config for a device. Read-only."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(c, "/v1.0/config/system", {"deviceSn": device_sn})
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_config_battery(device_sn: str) -> str:
    """Read battery parameters (max currents, capacities). Read-only."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(c, "/v1.0/config/battery", {"deviceSn": device_sn})
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_config_tou(device_sn: str) -> str:
    """Read time-of-use configuration. Read-only."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(c, "/v1.0/config/tou", {"deviceSn": device_sn})
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_device_measure_points(device_sn: str, device_type: str = "INVERTER") -> str:
    """List available measurement points for a device."""
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(
            c,
            "/v1.0/device/measurePoints",
            {"deviceSn": device_sn, "deviceType": device_type},
        )
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_station_history(
    station_id: int, start_at: str, granularity: int, end_at: str = ""
) -> str:
    """Get station historical data. granularity: 1=hourly,4=daily, etc."""
    body = {
        "stationId": station_id,
        "startAt": start_at,
        "granularity": granularity,
    }
    if end_at:
        body["endAt"] = end_at
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(c, "/v1.0/station/history", body)
        return json.dumps(res, ensure_ascii=False)


@mcp.tool()
async def get_device_history(
    device_sn: str,
    start_at: str,
    granularity: int,
    end_at: str = "",
    measure_points: list[str] = None,
) -> str:
    """Get device historical data. measure_points e.g. ['SOC','TotalConsumptionPower']."""
    body = {
        "deviceSn": device_sn,
        "startAt": start_at,
        "granularity": granularity,
    }
    if end_at:
        body["endAt"] = end_at
    if measure_points:
        body["measurePoints"] = measure_points
    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(c, "/v1.0/device/history", body)
        return json.dumps(res, ensure_ascii=False)


# ─── TWO-STEP CONTROL (propose → confirm) ─────────────────────────────────


@mcp.tool()
async def propose_control_change(
    device_sn: str, action_type: str, params: dict
) -> str:
    """
    PROPOSE a control change. Does NOT execute anything.

    Allowed action_type values and their params:
      - "set_work_mode":         params = {"mode": "SELLING_FIRST"}
      - "set_energy_pattern":    params = {"pattern": "BATTERY_FIRST"}
      - "set_solar_sell":        params = {"action": "on"}
      - "set_tou_switch":        params = {"action": "on", "days": ["MONDAY",...]}
      - "set_tou_update":        params = {"items": [{...6x TimeUseSettingItem}]}
      - "set_battery_type":      params = {"batteryType": "BATT_V"}
      - "set_battery_param":     params = {"parameter_type": "MAX_CHARGE_CURRENT", "value": 20}
      - "set_power_limit":       params = {"power_type": "MAX_SOLAR_POWER", "value": 5000}
      - "set_limit_control":     params = {"function_type": "ZERO_EXPORT_TO_LOAD"}
      - "set_grid_peak_shaving": params = {"action": "on", "power": 3000}
      - "set_battery_mode":      params = {"action": "on", "mode_type": "GEN_CHARGE"}
      - "set_smartload":         params = {"onGridAlwaysOn": false}

    Returns a proposal_id and a human-readable summary. The user must explicitly
    confirm before you call confirm_control_change().
    """
    # Validate device
    if device_sn not in ALLOWED_DEVICES:
        return json.dumps(
            {
                "error": f"Device {device_sn} not in allowed list. Allowed: {sorted(ALLOWED_DEVICES)}"
            },
            ensure_ascii=False,
        )

    if action_type not in ACTION_MAP:
        return json.dumps(
            {
                "error": f"Unknown action_type '{action_type}'. Allowed: {list(ACTION_MAP.keys())}"
            },
            ensure_ascii=False,
        )

    path, build = ACTION_MAP[action_type]
    try:
        body = build(device_sn, params)
    except KeyError as e:
        return json.dumps(
            {"error": f"Missing required param for {action_type}: {e}"},
            ensure_ascii=False,
        )

    proposal_id = str(uuid.uuid4())[:8]
    proposals = _load_proposals()
    proposals[proposal_id] = {
        "path": path,
        "body": body,
        "device_sn": device_sn,
        "action_type": action_type,
        "created_at": time.time(),
    }
    _save_proposals(proposals)

    return json.dumps(
        {
            "status": "pending_user_confirmation",
            "proposal_id": proposal_id,
            "summary": f"Will execute '{action_type}' on device '{device_sn}' → {body}",
            "instructions": (
                "Show this summary to the user. If they EXPLICITLY confirm "
                "(e.g. 'yes', 'confirm', 'do it'), call confirm_control_change "
                "with this proposal_id. Otherwise, discard it."
            ),
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def confirm_control_change(proposal_id: str) -> str:
    """
    EXECUTE a previously proposed control change.
    Requires a valid proposal_id from propose_control_change.
    Once executed, the proposal is consumed (cannot be replayed).
    """
    proposals = _load_proposals()
    if proposal_id not in proposals:
        return json.dumps(
            {
                "error": "Invalid, expired, or already-used proposal_id. Re-propose if needed."
            },
            ensure_ascii=False,
        )

    proposal = proposals.pop(proposal_id)
    _save_proposals(proposals)

    log.warning(
        "EXECUTING CONTROL: %s on %s body=%s",
        proposal["action_type"],
        proposal["device_sn"],
        proposal["body"],
    )

    async with httpx.AsyncClient(timeout=60) as c:
        res = await deye_post(c, proposal["path"], proposal["body"])

    return json.dumps(
        {
            "status": "executed",
            "action_type": proposal["action_type"],
            "device_sn": proposal["device_sn"],
            "result": res,
        },
        ensure_ascii=False,
    )


# ─── Entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Deye Secure Proxy MCP starting (stdio transport)...")
    mcp.run(transport="stdio")
