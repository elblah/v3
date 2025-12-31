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
- Enabled plugins in `.aicoder/plugins/` (per-project)
- Each plugin exports `create_plugin(context)` function
- Plugins can register tools, commands, and hooks
- Context provides access to full app via `ctx.app`

### Available Tools (for AI use)

#### Internal Tools
All tools return dict with `tool`, `friendly`, and `detailed` keys:

1. **read_file** - Read file with pagination
   - Parameters: `path` (required), `offset` (default: 0), `limit` (default: 2000)
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

6. **list_directory** - List files recursively
   - Parameters: `path` (default: current directory)

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
TEMPERATURE                          # Temperature (default: 0.0)
MAX_TOKENS                           # Max tokens (optional)

# Behavior
DEBUG=1                              # Debug mode
YOLO_MODE=1                          # Auto-approve all tool actions
MINI_SANDBOX=0                       # Disable file sandbox

# Performance
CONTEXT_SIZE=128000                  # Context window size
CONTEXT_COMPACT_PERCENTAGE=0         # Auto-compact threshold (%)
MAX_TOOL_RESULT_SIZE=300000          # Max tool output size
MAX_RETRIES=3                        # API retry attempts

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
- Handle file errors by re-reading before editing
- Use edit_file/write_file over shell commands when possible

### Plugin Context for Development
When working with plugins:
```python
def create_plugin(ctx):
    # Register tool for AI
    def my_tool(args):
        return {"tool": "mytool", "friendly": "msg", "detailed": "output"}
    ctx.register_tool('mytool', my_tool, 'Description', parameters)
    
    # Access app components
    ctx.app.message_history.add_user_message("Message")
    ctx.app.tool_manager.execute_tool_call(tool_call)
```

### Sandbox Behavior
- Blocks `../` path traversal by default
- Restricts absolute paths to current directory
- Can be disabled with `MINI_SANDBOX=0`
- Both read_file and write_file respect sandbox

### Streaming and Error Handling
- Uses Server-Sent Events (SSE) format
- Implements exponential backoff retry: 2s, 4s, 8s, 16s, 32s, 64s
- Shows retry progress: "Attempt 1/3 failed: <error>. Retrying in 2s..."
- Timeout handling per retry attempt