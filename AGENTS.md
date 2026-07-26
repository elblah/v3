# AI Coder — AI-assisted dev tool (Python stdlib only, zero deps)

## Constraints (unobservable from code)
- **Sandbox**: Only cwd and /tmp are writable. `~/.config/` and outside cwd are READ-ONLY. /tmp is sandbox-isolated — files there are invisible to external processes (dtx, vision, user). Only use /tmp for transient files the AI itself consumes.
- **Scope**: Only modify files within cwd unless explicitly asked.
- **Plugin dirs**: `aicoder/plugins/` auto-loaded. `examples/plugins/` NOT auto-loaded. Priority: `.aicoder/plugins/` > `~/.config/aicoder-v3/plugins/` > `aicoder/plugins/`.
