# Python Runtime Plugin

**Warning: Advanced Feature - Use with Caution**

The Python Runtime Plugin allows AI Coder to execute Python code inline within its own process, giving the AI full access to all internal components and state.

## Overview

This plugin provides:

- **`run_inline_python` tool**: Execute Python code with full AI Coder context
- **`/python_runtime` command**: Enable/disable the feature
- **Safety**: Never auto-approved, starts disabled by default

## Use Cases

### Debug AI Coder as It Runs
```python
# Inspect current state
print(f"Messages: {len(app.message_history.get_messages())}")
print(f"CWD: {app.input_handler.cwd}")
print(f"Stats: {app.stats.tokens_sent}")
```

### Update Working Directory After Moving Session
```python
# Your use case - update CWD after moving session
app.input_handler.cwd = "/new/path/to/session"
print("Working directory updated")
```

### Monkey Patch Behavior
```python
# Intercept API calls for debugging
original_method = app.streaming_client.send_request
def patched_request(*args, **kwargs):
    print(f"[DEBUG] API call: {kwargs}")
    return original_method(*args, **kwargs)
app.streaming_client.send_request = patched_request
```

### Modify System Prompt
```python
# Change the system prompt dynamically
messages = app.message_history.get_messages()
for msg in messages:
    if msg['role'] == 'system':
        msg['content'] = "New system prompt: You are now in debug mode"
        print("System prompt updated")
```

### Inspect Tool Configuration
```python
# List all available tools
for name, tool_def in app.tool_manager.tools.items():
    auto = "AUTO" if tool_def.get('auto_approved') else "MANUAL"
    print(f"{name}: {auto}")
```

### Access Plugin System
```python
# List loaded plugins
plugin_tools = app.plugin_system.get_plugin_tools()
print(f"Loaded plugins: {list(plugin_tools.keys())}")
```

## Commands

### `/python_runtime` - Control the Feature

```bash
# Show help
/python_runtime

# Enable Python Runtime (AI can use the tool)
/python_runtime on

# Disable Python Runtime
/python_runtime off

# Check current status
/python_runtime status
```

## Tool

### `run_inline_python` - Execute Python Code

The AI will use this tool when enabled. Each execution requires user approval.

**Parameters:**
- `code` (required): Python code to execute

**Available in Code:**
- `app`: AICoder instance - access all components
- `ctx`: PluginContext instance
- `print`: print function

## Safety Features

### ✅ Safe by Default
- Feature starts **DISABLED**
- Must explicitly run `/python_runtime on` to enable
- Clear status indicator

### ✅ Per-Execution Approval
- Every code execution requires user approval
- Approval prompt shows:
  - Current status (ENABLED/DISABLED)
  - Available context variables
  - Code to execute (truncated to 10 lines)
  - Warning about potential risks

### ✅ Explicit Control
- `/python_runtime status` shows current state
- Can disable anytime with `/python_runtime off`
- Plugin can be uninstalled to remove completely

## Available Context

When code executes, it has access to:

```python
app  # AICoder instance with:
     # - app.message_history: MessageHistory
     # - app.tool_manager: ToolManager
     # - app.streaming_client: StreamingClient
     # - app.input_handler: InputHandler
     # - app.plugin_system: PluginSystem
     # - app.stats: Stats
     # - app.context_bar: ContextBar
     # - app.socket_server: SocketServer
     # - etc.

ctx  # PluginContext instance with:
     # - ctx.app: AICoder instance (same as above)
     # - ctx.register_tool(): Register tools
     # - ctx.register_command(): Register commands
     # - ctx.register_hook(): Register event hooks

print # Python's print function
```

## Example Session

```bash
$ /python_runtime on
[*] Runtime Python ENABLED
    AI can now use run_inline_python tool (each execution requires approval)

> Update the working directory to /home/user/project

# AI will use the tool...
[*] Tool: run_inline_python
Runtime Python: ENABLED

Available in code:
  app  - AICoder instance (full access to all components)
  ctx  - PluginContext instance
  print - print function

Code to execute:
app.input_handler.cwd = "/home/user/project"
print("Working directory updated")

Approve [Y/n]: y
✓ Code executed successfully

$ /python_runtime status
[*] Runtime Python: ENABLED
```

## Risks and Warnings

⚠️ **When enabled, AI can:**

- **Modify internal state** - Change any attribute of any component
- **Corrupt sessions** - Modify message history, break state invariants
- **Remove guards** - Patch safety checks, disable warnings
- **Break the instance** - Cause crashes, infinite loops, memory leaks
- **Execute arbitrary code** - Any Python code in the process context

⚠️ **This is NOT safe for:**

- Untrusted AI models
- Production environments
- Systems with sensitive data
- Automated workflows without supervision

✅ **This IS safe for:**

- Trusted AI models you control
- Development and debugging
- Quick fixes without restarting
- Learning how AI Coder works internally
- Advanced users who understand the risks

## Installation

The plugin is automatically loaded if placed in:

- `.aicoder/plugins/` (project-specific, takes precedence)
- `~/.config/aicoder-v3/plugins/` (global)

To install:

```bash
# Copy plugin to project
cp plugins/python_runtime.py .aicoder/plugins/

# Or install globally
mkdir -p ~/.config/aicoder-v3/plugins
cp plugins/python_runtime.py ~/.config/aicoder-v3/plugins/
```

## Troubleshooting

### Tool Not Available
```bash
# Check if feature is enabled
/python_runtime status

# Enable if needed
/python_runtime on
```

### Code Execution Errors
Check the detailed output for:
- Variable names typos
- Missing imports (use `import` statements)
- AttributeError (check available context)
- Syntax errors

### Plugin Not Loading
```bash
# Check plugin exists
ls .aicoder/plugins/python_runtime.py
# or
ls ~/.config/aicoder-v3/plugins/python_runtime.py

# Check for syntax errors
python3 -m py_compile .aicoder/plugins/python_runtime.py
```

## Technical Details

### Plugin Architecture

The plugin uses a closure-based state management:

```python
_state = {
    "enabled": False,  # Feature starts disabled
    "ctx": ctx         # Reference to plugin context
}
```

This allows:
- Plugin state without complex classes
- Direct access to AI Coder via `ctx.app`
- Clean separation of concerns
- Simple enable/disable toggle

### Code Execution

Uses Python's `exec()` with a custom global namespace:

```python
execution_globals = {
    "app": _state["ctx"].app,
    "ctx": _state["ctx"],
    "print": print,
    "__name__": "__runtime__",
}

exec(code, execution_globals)
```

Output is collected from newly created variables (excluding built-ins).

### Tool Registration

The tool is registered with:
- `auto_approved=False` - Always requires approval
- `format_arguments` - Custom approval display
- Clear description of risks

## Contributing

This plugin demonstrates:
- Tool registration with custom approval formatting
- Command registration for user control
- State management in closures
- Safe defaults with explicit opt-in
- Comprehensive error handling

## License

Same as AI Coder project.

## Support

For issues or questions:
1. Check this documentation
2. Review the test file: `test_python_runtime_plugin.py`
3. Check AI Coder main documentation
4. Open an issue on the project repository
