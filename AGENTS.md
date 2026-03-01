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
2. **Sandbox aware** - File operations restricted to current directory by default
3. **Structured tool returns** - All tools must return `tool`, `friendly`, `detailed` dict
4. **DO NOT** write to ~/.config/* or local .aicoder/* directories
5. **DO NOT** try to install global plugins or snippets
6. **Plugins directory** - The `plugins/` folder in project root is the ONLY place for plugins. Do NOT look in `.aicoder/plugins` or `~/.config/aicoder-v3/plugins`

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

## Common Patterns to Avoid
- Don't mention something in AGENTS.md just to document it - this biases the model toward it
- If the model can find it in the codebase, it doesn't need to be here
