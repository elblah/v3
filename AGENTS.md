# AI Coder - Agent Context

## Project Overview
AI Coder is a fast, lightweight AI-assisted development tool. Built using only Python standard library with no external dependencies.

## Architecture Principles
- **No external dependencies** - uses only Python stdlib
- **Simple and direct** - minimal abstractions, clear code flow
- **Working over perfect** - prioritize functionality over elegance
- **Stay in scope** - only modify files within current working directory unless explicitly asked

## Key Constraints
1. **Prefer system tools** - Use diff, ripgrep, find when available
2. **File write sandbox** - Only the current working directory and /tmp are writable. `~/.config/` and all directories outside cwd are READ-ONLY. Any write attempts outside cwd will fail. Files in /tmp are temporary (memory-backed, cleared on reboot).
3. **Structured tool returns** - All tools must return `tool`, `friendly`, `detailed` dict
4. **DO NOT** write to ~/.config/* or local .aicoder/* directories
5. **DO NOT** try to install global plugins or snippets
6. **Two plugin directories:**
   - `aicoder/plugins/` - Core plugins, auto-loaded by PluginSystem (generically useful, e.g. shell, memory, git_aware, ruff)
   - `examples/plugins/` - Optional/example plugins, NOT auto-loaded (specialized: a11y, audio, tts, etc.)
   Plugin loading priority: `.aicoder/plugins/` > `~/.config/aicoder-v3/plugins/` > `aicoder/plugins/`

## Core Components
- `aicoder/core/aicoder.py` - Main application orchestrator
- `aicoder/core/streaming_client.py` - AI API communication (urllib, no requests)
- `aicoder/core/tool_manager.py` - Tool management
- `aicoder/core/plugin_system.py` - Plugin loader

## Color Usage
Always use `Config.colors` - never hardcode ANSI codes:
```python
from aicoder.core.config import Config
print(f"{Config.colors['green']}[+] Done{Config.colors['reset']}")
```

## tmux Integration
- Core commands (`edit`, `edit-session`, `memory`) use tmux for editor popups
- `examples/tmux-popup-menu.sh` - Interactive popup menu for stop/yolo/commands
- `examples/tmux-status.sh` - Status bar indicator for AI Coder state
- Socket API is tmux-aware (uses `TMUX_PANE` in socket path)

## Common Patterns to Avoid
- Don't mention something in AGENTS.md just to document it - this biases the model toward it
- If the model can find it in the codebase, it doesn't need to be here
