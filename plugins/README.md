# AI Coder v3 - Plugin System

Ultra-fast, minimalist plugin system using duck typing.

## How It Works

1. Available plugins live in `plugins/` (tracked in git)
2. Enabled plugins live in `.aicoder/plugins/` (per-project, gitignored)
3. Each plugin is a single `.py` file
4. Plugin exports `create_plugin(context)` function
5. Files starting with `_` are disabled (e.g., `_ruff.py`)

## Installing Plugins

### For New Projects

```bash
# Copy only plugins you want
cp plugins/web_search.py .aicoder/plugins/
cp plugins/notify_prompt.py .aicoder/plugins/

# Or copy all available plugins
cp plugins/*.py .aicoder/plugins/
```

### For Existing Projects (using current setup)

You're already good - `.aicoder/plugins/` is populated.

### Disabling a Plugin

```bash
# Option 1: Remove file
rm .aicoder/plugins/ruff.py

# Option 2: Rename with _ prefix (files starting with _ are ignored)
mv .aicoder/plugins/ruff.py .aicoder/plugins/_ruff.py
```

### Re-enabling a Plugin

```bash
# Copy from available plugins
cp plugins/ruff.py .aicoder/plugins/

# Or rename back
mv .aicoder/plugins/_ruff.py .aicoder/plugins/ruff.py
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
- The global plugin loader message `[i] Loading plugins from...` is always shown

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
