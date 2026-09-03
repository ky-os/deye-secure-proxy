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

## Setup

```bash
cd e:\deye-secure-proxy
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe "mcp>=1.0,<2.0" httpx
```

Create `~/.deye/credentials.env` (see `credentials.env.example` format).

## Hermes Config

```yaml
mcp_servers:
  deye-secure-proxy:
    command: C:\Users\Admin\.deye\proxy\.venv\Scripts\python.exe
    args: ["C:\Users\Admin\.deye\proxy\deye_secure_proxy.py"]
    transport: stdio
    enabled: true
  deye_open:
    enabled: false
```

## Agent-Visible Tools

### Read-only
- `list_stations`, `get_station_latest`, `list_station_devices`
- `get_device_latest`, `get_station_alerts`, `get_device_alerts`
- `get_config_system`, `get_config_battery`, `get_config_tou`
- `get_device_measure_points`, `get_station_history`, `get_device_history`

### Control (two-step)
- `propose_control_change(device_sn, action_type, params)` → returns `proposal_id`
- `confirm_control_change(proposal_id)` → executes (one-shot)

See `deye-open-mcp` skill for full `action_type` list and allowed devices.

## Security

- Credentials never leave the proxy process
- Device whitelist: only `2507120169` and `2305202443` accepted for control
- Token cached to `~/.deye/.token_cache.json` (chmod 600)
- `call_deye_api` and `get_access_token` are NOT exposed

## License

MIT
