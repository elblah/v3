# AI Coder - Agent Context

## Project Overview
AI Coder is a fast, lightweight AI-assisted development. Built using only Python standard library with no external dependencies.

## Architecture Principles
- **No external dependencies** - uses only Python stdlib
- **Simple and direct** - minimal abstractions, clear code flow
- **Working over perfect** - prioritize functionality over elegance
- **Systematic approach** - incremental progress with clear verification
- **Stay in scope** - only modify files within the current working directory unless explicitly asked by the user to work elsewhere

## Core Architecture

### Main Components
- **AICoder** (`/aicoder/core/aicoder.py`) - Main application orchestrator
- **StreamingClient** (`/aicoder/core/streaming_client.py`) - Handles AI API communication using urllib
- **ToolManager** (`/aicoder/core/tool_manager.py`) - Manages available tools for AI to use
- **PluginSystem** (`/aicoder/core/plugin_system.py`) - Ultra-fast plugin loader
- **MessageHistory** (`/aicoder/core/message_history.py`) - Conversation state management
- **SessionManager** (`/aicoder/core/session_manager.py`) - AI session workflow
- **Config** (`/aicoder/core/config.py`) - Environment-based configuration

### Plugin System
- Plugins source code in plugins dir (./plugins in the project root)
- The user is responsible for installing / updating plugins
- Each plugin exports `create_plugin(context)` function
- Plugins can register tools, commands, and hooks
- Context provides access to full app via `ctx.app`

### Configuration (Environment Variables)
Variables that affect AI behavior:
```bash
# API Configuration
API_BASE_URL or OPENAI_BASE_URL     # API endpoint
API_KEY or OPENAI_API_KEY            # Authentication (optional)
API_MODEL or OPENAI_MODEL            # Model name

# Behavior
DEBUG=1                              # Debug mode
YOLO_MODE=1                          # Auto-approve all tool actions
MINI_SANDBOX=0                       # Disable file sandbox
TOOLS_ALLOW=read_file,grep            # Restrict available tools (comma-separated)
PLUGINS_ALLOW=web_search,git_aware   # Restrict loaded plugins (comma-separated, without .py)

# Performance
CONTEXT_SIZE=128000                  # Context window size
CONTEXT_COMPACT_PERCENTAGE=0         # Auto-compact threshold (%)
MAX_TOOL_RESULT_SIZE=20000           # Max tool output size
MAX_RETRIES=10                       # API retry attempts

# Timeouts (seconds)
TOTAL_TIMEOUT=300                    # Total timeout for HTTP requests
```

### Key Constraints
1. **Prefer system tools** - Use diff, ripgrep, find when available
2. **Sandbox aware** - File operations restricted to current directory by default
3. **Structured tool returns** - All tools must return `tool`, `friendly`, `detailed` dict
4. DO NOT TRY install global plugins, snippets, DO NOT write to ~/.config/*  nor local .aicoder/* dir at all

### File Structure
```
aicoder/
├── core/                 # Core application components
│   ├── aicoder.py       # Main application
│   ├── config.py        # Configuration management
│   ├── streaming_client.py  # AI API communication
│   ├── tool_manager.py  # Tool management
│   ├── plugin_system.py    # Plugin system
│   └── ...
├── tools/
│   └── internal/         # Built-in tools
└── plugins/              # Available plugins
```

### Development Guidelines
- Keep comments professional and functional
- Focus on what code does, not implementation details
- Single responsibility principle
- Early exits and guard clauses
- Batch operations efficiently
- When using tools, handle file errors by re-reading before editing
- Use edit_file/write_file over shell commands like sed, awk, custom scripts in any language with the objective to mass edit

### Color Usage Guidelines
Always use `Config.colors` - never hardcode ANSI codes. This applies to **all** code including tests. Plugins may override colors, so hardcoded values will look inconsistent.

```python
from aicoder.core.config import Config

# Correct
print(f"{Config.colors['green']}[+] Done{Config.colors['reset']}")

# Wrong - hardcoded escape sequences
print("\x1b[32m[+] Done\x1b[0m")
```
