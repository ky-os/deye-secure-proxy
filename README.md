# deye-secure-proxy

Local secure MCP server for Deye Cloud access. Runs as a stdio MCP process,
reads `~/.deye/credentials.env` internally, and exposes only curated tools.
The AI agent never sees credentials or access tokens.

## Architecture

```
Agent / LLM
   │  calls curated tools (no credentials in args)
   ▼
deye-secure-proxy (stdio MCP)
   │  reads ~/.deye/credentials.env
   │  obtains + caches Deye access token
   │  enforces device whitelist on control actions
   ▼
DeyeCloud OpenAPI (https://eu1-developer.deyecloud.com)
```

## Quick Start

```bash
# Clone
git clone https://github.com/ky-os/deye-secure-proxy.git
cd deye-secure-proxy

# Setup venv
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt

# Credentials (see credentials.env.example for format)
mkdir -p ~/.deye
cp credentials.env.example ~/.deye/credentials.env
# then edit with your real values

# Install skills into Hermes
cp -r skills/* ~/.hermes/skills/

# Wire into Hermes config (~/.hermes/config.yaml):
#   mcp_servers:
#     deye-secure-proxy:
#       command: <REPO_ROOT>/.venv/Scripts/python.exe
#       args: ["<REPO_ROOT>/deye_secure_proxy.py"]
#       transport: stdio
#       enabled: true
#     deye_open:
#       enabled: false

# Restart Hermes — list_stations() should work with no auth step.
```

> On macOS/Linux, `.venv/Scripts/python` → `.venv/bin/python`.

## Agent-Visible Tools

### Read-only (always safe)
- `list_stations`, `get_station_latest`, `list_station_devices`
- `get_device_latest`, `get_station_alerts`, `get_device_alerts`
- `get_config_system`, `get_config_battery`, `get_config_tou`
- `get_device_measure_points`, `get_station_history`, `get_device_history`

### Control (two-step confirmation)
- `propose_control_change(device_sn, action_type, params)` → returns `proposal_id`
- `confirm_control_change(proposal_id)` → executes (one-shot, consumed)

See `skills/deye-open-mcp/SKILL.md` for full `action_type` list and allowed devices.

## Skills (Hermes Agent)

| Skill | Purpose |
|---|---|
| `deye-open-mcp` | Tool map, safety rules, troubleshooting |
| `deye-hybrid-solar-analysis` | Battery sizing, bill-to-zero, solar review |
| `deye-inverter-config-review` | Read-only config audit |

## Security

- Credentials never leave the proxy process
- Device whitelist: only `2507120169` and `2305202443` accepted for control
- Token cached to `~/.deye/.token_cache.json` (chmod 600)
- `call_deye_api` and `get_access_token` are NOT exposed
- `*.env` and `.token_cache.json` are in `.gitignore`

## License

MIT
