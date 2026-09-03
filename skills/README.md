# Hermes Skills

These are the Hermes Agent skills for using the Deye Secure Proxy MCP.
Copy them into `~/.hermes/skills/` (or use `hermes skill install` if supported).

## Install

```bash
# Copy the skill directories into Hermes skills folder
cp -r skills/* ~/.hermes/skills/
```

Restart Hermes after copying.

## Skills

| Skill | Purpose |
|---|---|
| `deye-open-mcp` | Documents the proxy tool surface, safety rules, and troubleshooting |
| `deye-hybrid-solar-analysis` | Solar config review, battery sizing, bill-to-zero analysis |
| `deye-inverter-config-review` | Read-only inverter config audit with discrepancy detection |
