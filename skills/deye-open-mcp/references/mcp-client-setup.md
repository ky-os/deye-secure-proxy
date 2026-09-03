# MCP Client Setup (Local Secure Proxy)

This reference documents the **local secure proxy** for Deye Cloud access.

The `deye-secure-proxy` MCP server runs as a local stdio process, reads
`~/.deye/credentials.env` internally, and exposes only curated tools.
The agent never sees credentials or access tokens.

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

## Hermes Agent Configuration

`~/.hermes/config.yaml`:

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

After editing config, restart Hermes or run `/reload-mcp`.

## Smoke Test

```text
Load the deye-open-mcp skill. List my Deye stations.
```

Expected tool behavior:
- Call `list_stations(page=1, size=10)` directly — no auth step needed.
- Returns stations array with id, name, status, batterySOC, generationPower.

## Credential File Format

`~/.deye/credentials.env`:

```
DEYE_APP_ID=...
DEYE_APP_SECRET=...
DEYE_EMAIL=...
DEYE_PASSWORD=...
DEYE_DATA_CENTER=eu
```

## Files

| Path | Purpose |
|---|---|
| `~/.deye/proxy/deye_secure_proxy.py` | Proxy MCP server |
| `~/.deye/proxy/.venv/` | Python venv (mcp + httpx) |
| `~/.deye/credentials.env` | Credentials (chmod 600 recommended) |
| `~/.deye/.token_cache.json` | Token cache (chmod 600, auto-managed) |

## Security Rules

- Never pass `app_secret`, `password`, or `access_token` as tool arguments.
- The proxy never returns credentials in tool output.
- Device whitelist enforced: only `2507120169` and `2305202443` accepted for control.
- Control actions require `propose_control_change` → user confirmation → `confirm_control_change`.
