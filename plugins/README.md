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
cp plugins/01_web_search.py .aicoder/plugins/
cp plugins/02_notify_prompt.py .aicoder/plugins/

# Or copy all available plugins
cp plugins/*.py .aicoder/plugins/
```

### For Existing Projects (using current setup)

You're already good - `.aicoder/plugins/` is populated.

### Disabling a Plugin

```bash
# Option 1: Remove file
rm .aicoder/plugins/03_ruff.py

# Option 2: Rename with _ prefix (files starting with _ are ignored)
mv .aicoder/plugins/03_ruff.py .aicoder/plugins/_03_ruff.py
```

### Re-enabling a Plugin

```bash
# Copy from available plugins
cp plugins/03_ruff.py .aicoder/plugins/

# Or rename back
mv .aicoder/plugins/_03_ruff.py .aicoder/plugins/03_ruff.py
```

## Plugin API

```python
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
- `before_approval_prompt` - Before showing tool approval
- `before_file_write(path, content)` - Before writing file (can return modified content)
- `after_file_write(path, content)` - After file is written (file exists at this point)
- `after_tool_results(tool_results)` - After tool results are added to message history (safe time to add plugin messages)

## Available Plugins

- `01_web_search.py` - Web search and URL content fetching
  - Tools: `web_search` (auto-approved), `get_url_content`
  - Requires: lynx browser
  - Uses: DuckDuckGo Lite with correct URL and user agent

- `02_notify_prompt.py` - Audio notifications for prompts/approvals
  - Hooks: `before_user_prompt`, `before_approval_prompt`
  - Requires: espeak, pulseaudio/pipewire
  - Features: HDMI audio sink detection

- `03_ruff.py` - Python code quality checks
  - Commands: `/ruff on/off`, `/ruff check-serious on/off`
  - Hooks: `after_file_write` (runs after file is created/updated)
  - Requires: ruff linter

- `04_luna_theme.py` - Luna color theme
  - Applies Luna color palette with soft pink/magenta, lime green, gold, and light cyan tones
  - Updates `Config.colors` with Luna's true color RGB values
  - No dependencies - pure Python stdlib
