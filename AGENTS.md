# AI Coder - Agent Context

## Project Overview
AI Coder is a fast, lightweight AI-assisted development tool that runs anywhere. Built using only Python standard library with no external dependencies.

## Architecture Principles
- **No external dependencies** - uses only Python stdlib
- **Simple and direct** - minimal abstractions, clear code flow
- **Working over perfect** - prioritize functionality over elegance
- **Systematic approach** - incremental progress with clear verification

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
Ultra-fast plugin system:
- Available plugins in `plugins/` directory
- Each plugin exports `create_plugin(context)` function
- Plugins can register tools, commands, and hooks
- Context provides access to full app via `ctx.app`

### Available Tools (for AI use)

#### Internal Tools
All tools return dict with `tool`, `friendly`, and `detailed` keys:

1. **read_file** - Read file with pagination
   - Parameters: `path` (required), `offset` (optional), `limit` (optional)
   - Sandbox: Blocks access outside current directory unless `MINI_SANDBOX=0`

2. **write_file** - Write file with preview and hooks
   - Parameters: `path` (required), `content` (required)
   - Supports plugin hooks: `before_file_write`, `after_file_write`

3. **edit_file** - Edit file with exact text replacement
   - Parameters: `path` (required), `old_string` (required), `new_string` (required)

4. **run_shell_command** - Execute shell commands
   - Parameters: `command` (required), `timeout` (default: 30), `cwd` (optional)
   - Can be auto-approved with `YOLO_MODE=1`

5. **grep** - Search text using ripgrep
   - Parameters: `text` (required), `path` (default: current), `max_results`, `context`

6. **list_directory** - List files recursively with optional pattern matching
   - Parameters: `path` (default: current directory), `pattern` (optional glob like `*.py`)

#### Plugin Tools
Plugins can add additional tools. Common plugin tools:
- `web_search` - Web search via DuckDuckGo
- `get_url_content` - Fetch URL content

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

# Performance
CONTEXT_SIZE=128000                  # Context window size
CONTEXT_COMPACT_PERCENTAGE=0         # Auto-compact threshold (%)
MAX_TOOL_RESULT_SIZE=20000           # Max tool output size
MAX_RETRIES=10                       # API retry attempts

# Timeouts (seconds)
STREAMING_TIMEOUT=300                # Streaming timeout
STREAMING_READ_TIMEOUT=30            # Read timeout
TOTAL_TIMEOUT=300                    # Total timeout
```

### Key Constraints
1. **No external dependencies** - Must use only Python stdlib
2. **Use urllib** for HTTP requests (no requests library)
3. **Prefer system tools** - Use diff, ripgrep, find when available
4. **Sandbox aware** - File operations restricted to current directory by default
5. **Structured tool returns** - All tools must return `tool`, `friendly`, `detailed` dict

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

### Plugin Context for Development
When working with plugins:
```python
from aicoder.core.config import Config

def create_plugin(ctx):
    # Register tool for AI
    def my_tool(args):
        return {"tool": "mytool", "friendly": "msg", "detailed": "output"}
    ctx.register_tool('mytool', my_tool, 'Description', parameters)

    # Access app components
    ctx.app.message_history.add_user_message("Message")
    ctx.app.tool_manager.execute_tool_call(tool_call)

    # Suppress plugin loading messages unless DEBUG=1
    if Config.debug():
        print("[+] My plugin loaded")
        print("    - mytool tool")
```

### Plugin Output Conventions
Plugins should suppress verbose loading messages by default and only show them when `DEBUG=1`:

```python
from aicoder.core.config import Config

def create_plugin(ctx):
    # Only print info messages when DEBUG=1
    if Config.debug():
        print("[+] My plugin loaded")
        print("    - /mycmd command")

    # Always print errors (missing requirements, etc.)
    if not requirements_ok:
        print(f"[!] My plugin unavailable - missing requirements:")
        for req in missing:
            print(f"    - {req}")
```

**Why?**
- Clean startup: No verbose "[+] Plugin X loaded" messages by default
- Debug mode: Use `DEBUG=1 aicoder` to see all plugin loading details
- Error visibility: Missing requirements or configuration errors are always shown

**To debug plugin loading:**
```bash
DEBUG=1 aicoder
```
### Streaming and Error Handling
- Uses Server-Sent Events (SSE) format
- Implements exponential backoff retry: 2s, 4s, 8s, 16s, 32s, max_backoff (configurable, default 64s)
- Shows retry progress: "Attempt 1/3 failed: <error>. Retrying in 2s..."
- Timeout handling per retry attempt
- Configurable max backoff via `MAX_BACKOFF_SECONDS` env var or `/retry max_backoff` command

### Sandbox Behavior (when enabled)
- Blocks `../` path traversal by default
- Restricts absolute paths to current directory
- Can be disabled with `MINI_SANDBOX=0`
- Both read_file and write_file respect sandbox
- This mini sandbox is programmed in the tools but the aicoder is also running on another bwrap sandbox layer

### Sandbox bwrap
- Prevent AI from deleting / modifying
- ALLOW write-access to files ONLY in working directory and /tmp
- DO NOT TRY install global plugins, snippets, write to ~/.config dir at all
- ONLY change code of plugin, skills, snippets in its proper dir in the project dir
- Do not read/write to .aicoder on the project dir unless the user has authorized it or if any skill, tool, or system prompt asks for it. This prevents writing plugins that will be lost because git ignores files in these dirs. So the AI always operates in the project dirs where files are controlled by git and history is preserved.

