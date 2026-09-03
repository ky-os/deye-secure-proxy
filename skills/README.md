# Hermes Skills

Hermes Agent skills for the Deye Secure Proxy MCP.

## Install

```bash
# Linux / macOS / git-bash
cp -r skills/* ~/.hermes/skills/

# Windows (PowerShell)
xcopy /E /I skills\* $env:USERPROFILE\.hermes\skills\

# Windows (cmd)
xcopy /E /I skills\* %USERPROFILE%\.hermes\skills\
```

Restart Hermes after copying.

## Skills

| Skill | Purpose |
|---|---|
| `deye-open-mcp` | Tool surface + safety rules |
| `deye-hybrid-solar-analysis` | Solar config review, battery sizing, bill-to-zero |
| `deye-inverter-config-review` | Read-only config audit |

See each `SKILL.md` for full details.
