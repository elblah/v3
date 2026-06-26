# AI Coder v3 - Plugin System

Ultra-fast, minimalist plugin system using duck typing.

## 3-Tier Plugin Loading

Plugins load in priority order (first wins on name collision):

1. **Local** — `.aicoder/plugins/` (per-project, gitignored)
2. **Global** — `~/.config/aicoder-v3/plugins/` (user-wide)
3. **Bundled** — `aicoder/plugins/` (shipped with package, resolves from package location, not CWD)

Each plugin is a single `.py` file exporting `create_plugin(context)`. Files starting with `_` are disabled.

## Managing Plugins

### Disabling a Bundled Plugin

Add a file with same name to `.aicoder/plugins/` — local takes priority over bundled.

```bash
# Touch empty file to disable (local override wins)
touch .aicoder/plugins/web_search.py

# Or rename in bundled dir (won't survive package update)
mv aicoder/plugins/ruff.py aicoder/plugins/_ruff.py
```

### Disabling a Plugin (local/global)

```bash
# Option 1: Remove file
rm .aicoder/plugins/ruff.py

# Option 2: Rename with _ prefix
mv .aicoder/plugins/ruff.py .aicoder/plugins/_ruff.py
```

### Restricting Plugins with PLUGINS_ALLOW

You can restrict which plugins are loaded using the `PLUGINS_ALLOW` environment variable:

```bash
# Load only specific plugins (comma-separated, without .py extension)
PLUGINS_ALLOW="web_search,git_aware" aicoder

# Useful for subagents with limited capabilities
PLUGINS_ALLOW="" echo "Quick analysis" | aicoder

# Use with TOOLS_ALLOW for maximum security
PLUGINS_ALLOW="web_search" TOOLS_ALLOW="read_file,grep" aicoder
```

**Note:** `PLUGINS_ALLOW` filters by plugin filename (without `.py` extension), not by registered tool names.

**Use cases:**
- Performance: Disable unnecessary plugins for faster startup
- Security: Prevent network access by excluding `web_search`
- Isolation: Limit subagents to specific capabilities
- Testing: Test behavior with different plugin combinations

**Plugin locations:**
- Local: `.aicoder/plugins/` (project-specific, takes precedence)
- Global: `~/.config/aicoder-v3/plugins/` (user's global plugins)
- Bundled: `aicoder/plugins/` (ships with package, auto-loads)

```bash
# List plugins by tier
ls -la .aicoder/plugins/                  # Local (project)
ls -la ~/.config/aicoder-v3/plugins/      # Global (user)
ls -la aicoder/plugins/                   # Bundled (package)
```

## Plugin Output Conventions

To keep startup clean, plugins should wrap verbose output in `Config.debug()` checks:

```python
from aicoder.core.config import Config

def create_plugin(ctx):
    # This output only shows when DEBUG=1
    if Config.debug():
        print("[+] My plugin loaded")
        print("    - mytool tool")
        print("    - /mycmd command")

    # Always print errors (never wrap these)
    if requirements_missing:
        print(f"[!] My plugin unavailable - missing requirements:")
        for req in requirements_missing:
            print(f"    - {req}")
```

**Rules:**
- Wrap informational/verbose messages in `if Config.debug():`
- Always print errors (e.g., missing requirements) without conditions
- Plugin loading messages are gated on `Config.debug()` — silent in normal use

**To see plugin loading output:**
```bash
DEBUG=1 aicoder
```

## Plugin API

```python
from aicoder.core.config import Config

def create_plugin(ctx):
    """
    Called when plugin loads.

    ctx provides:

    Registration methods (elegant abstractions):
    - ctx.register_tool(name, fn, description, parameters, auto_approved=False)
    - ctx.register_command(name, handler, description=None)
    - ctx.register_hook(event_name, handler)

    Direct app access (bureaucracy-free):
    - ctx.app - Full AICoder instance with direct access to all components:
      - ctx.app.message_history - Message history management
      - ctx.app.tool_manager - Tool manager (execute tools directly)
      - ctx.app.streaming_client - AI client for making API calls
      - ctx.app.stats - Statistics tracking
      - ctx.app.session_manager - Session management
      - ctx.app.command_handler - Command registry
      - ctx.app.input_handler - User input handling
      - ctx.app.context_bar - Context bar display
    """

    # Register tool for AI (must return dict like internal tools)
    def my_tool(args):
        return {
            "tool": "mytool",
            "friendly": "Short msg",
            "detailed": "Full output"
        }
    ctx.register_tool('mytool', my_tool, 'My tool',
                     {'type': 'object', 'properties': {}}, auto_approved=True)

    # Register user command
    def my_cmd(args_str):
        print("Works!")
    ctx.register_command('/mycmd', my_cmd, 'My command')

    # Register event hook
    def on_event():
        print("Event triggered!")
    ctx.register_hook('before_user_prompt', on_event)

    # Add a message to the conversation (direct access, no bureaucracy)
    ctx.app.message_history.add_user_message("Plugin message")

    # Optional: Suppress plugin loading messages unless DEBUG=1
    if Config.debug():
        print("[+] My plugin loaded")
        print("    - /mycmd command")

    # Optional: return cleanup function
    def cleanup():
        print("Cleanup!")
    return {'cleanup': cleanup}
```

## Tool Return Format

Plugin tools MUST return a dict with `tool`, `friendly`, and `detailed` keys:

```python
def my_tool(args):
    return {
        "tool": "my_tool_name",     # Tool name
        "friendly": "Short msg",    # User-friendly message
        "detailed": "Full output"    # Full output for AI
    }
```

## Available Hooks

- `before_user_prompt` - Before showing user input prompt
- `before_approval_prompt` - Before showing tool approval (can return `True`=auto-approve, `False`=auto-deny, `None`=ask user)
- `before_file_write(path, content)` - Before writing file (can return modified content)
- `after_file_write(path, content)` - After file is written (file exists at this point)
- `after_tool_results(tool_results)` - After tool results are added to message history (safe time to add plugin messages)

### Auto-Approve/Deny with `before_approval_prompt`

Plugins can intercept tool approval by returning a boolean from this hook:

```python
def before_approval_prompt(tool_name: str, arguments: dict) -> bool | None:
    """
    Called before approval prompt.

    Returns:
    - True  -> auto-approve (run the tool)
    - False -> auto-deny (cancel the tool)
    - None  -> ask user (default behavior)
    """
    if tool_name == "read_file":
        return True  # Auto-approve all file reads

    if tool_name == "run_shell_command":
        cmd = arguments.get("command", "")
        if cmd.startswith("rm "):
            print(f"[auto-deny] Dangerous command: {cmd}")
            return False  # Auto-deny rm commands

    return None  # Ask user for everything else

ctx.register_hook("before_approval_prompt", before_approval_prompt)
```

See `auto_approve.py` plugin for a regex-based implementation.

## Available Plugins

- `auto_approve.py` - Auto approve/deny tools based on regex rules
  - Hooks: `before_approval_prompt` (returns True/False/None)
  - Rules file: `.aicoder/auto-approve-rules.json`
  - Example: Auto-approve read_file, deny rm commands

- `web_search.py` - Web search and URL content fetching
  - Tools: `web_search` (auto-approved), `get_url_content`
  - Requires: lynx browser
  - Uses: DuckDuckGo Lite with correct URL and user agent

- `notify_prompt.py` - Audio notifications for prompts/approvals
  - Hooks: `before_user_prompt`, `before_approval_prompt`
  - Requires: espeak, pulseaudio/pipewire
  - Features: HDMI audio sink detection

- `ruff.py` - Python code quality checks
  - Commands: `/ruff on/off`, `/ruff check-serious on/off`
  - Hooks: `after_file_write` (runs after file is created/updated)
  - Requires: ruff linter

- `luna_theme.py` - Luna color theme
  - Applies Luna color palette with soft pink/magenta, lime green, gold, and light cyan tones
  - Updates `Config.colors` with Luna's true color RGB values
  - No dependencies - pure Python stdlib

- `summaron.py` - Round-based automatic context digestion
  - Commands: `/summaron status`, `/summaron set <N>`, `/summaron limit <N>`, `/summaron rounds`, `/summaron digest <N>`, `/summaron enable/disable`
  - Hooks: `after_user_message_added`, `after_assistant_message_added`, `after_tool_results_added`, `after_compaction`, `on_session_change`
  - Config: `SUMMARON_THRESHOLD` (default: 50%), `SUMMARON_LIMIT` (default: 100k), `SUMMARON_ENABLED` (default: 1)
  - Features: Automatic round creation, <summary> extraction, 50% working space, user message preservation
  - Use case: Prevents surprise auto-compaction by maintaining context at 50% automatically

- `tasks.py` - Task tracking for long autonomous sessions
  - Tools: `add_task`, `update_task`, `list_tasks`, `delete_task`, `clear_all_tasks`
  - Commands: `/tasks` (summary), `/task <id>` (details), `/task done <id>`, `/task cancel <id>`
  - Hooks: `before_user_prompt` (shows pending/in-progress tasks)
  - Storage: `.aicoder/tasks.json` (persistent)
  - Statuses: pending, in_progress, completed, cancelled
  - Use case: Maintains "harness" during long sessions to reduce AI drift

- `notes.py` - Persistent notes that survive compaction
  - Tools: `save_note(action="append|replace", content="<content>")`
  - Commands: `/notes` (show all notes)
  - Hooks: `before_compaction` (saves notes), `after_compaction` (restores notes)
  - Features: [NOTE] messages persist through compaction
  - Use case: Store important context (file locations, decisions, state, pending tasks)
