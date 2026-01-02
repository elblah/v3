# Python Runtime Plugin - Implementation Summary

## Overview

The **Python Runtime Plugin** has been successfully implemented! This advanced feature allows AI Coder to execute Python code inline within its own process, giving the AI full access to all internal components and state.

## What Was Implemented

### 1. Plugin File: `plugins/python_runtime.py`

A fully functional plugin that provides:

#### Tool: `run_inline_python`
- Executes Python code in AI Coder's runtime context
- Provides access to `app` (AICoder instance) and `ctx` (PluginContext)
- **Never auto-approved** - always requires user approval
- Shows clear warnings and code preview before execution
- Returns detailed output including any variables created

#### Command: `/python_runtime`
Control interface for the feature with subcommands:
- `on` - Enable the feature (AI can use the tool)
- `off` - Disable the feature
- `status` - Show current status
- (no args) - Show help

### 2. Documentation: `docs/PYTHON_RUNTIME.md`

Comprehensive documentation including:
- Overview and use cases
- Command and tool reference
- Safety features and warnings
- Available context variables
- Example sessions
- Troubleshooting guide
- Technical details

## Key Features

### ✅ Safety First

1. **Disabled by Default**: Feature starts disabled and must be explicitly enabled
2. **Per-Execution Approval**: Every code execution requires user approval
3. **Clear Warnings**: Approval prompt shows risks and code preview
4. **Explicit Control**: Easy to enable/disable at any time

### ✅ Powerful Capabilities

The AI can now:
- Debug AI Coder as it runs
- Monkey patch any behavior
- Update working directory (your original use case!)
- Modify system prompt dynamically
- Inspect internal state
- Access all components

### ✅ Clean Implementation

- Closure-based state management
- Follows AI Coder plugin patterns
- Proper error handling with tracebacks
- Custom approval formatting
- No external dependencies

## Use Case Example: Moving Sessions

Your original use case is now easy:

```bash
# 1. Move the saved session file to new directory
$ mv .aicoder/session.json /new/path/.aicoder/

# 2. Enable Python Runtime
$ /python_runtime on

# 3. Ask AI to update working directory
> The session was moved to /new/path, please update the working directory

# AI will use run_inline_python tool:
app.input_handler.cwd = "/new/path"

# 4. Approve when prompted
Approve [Y/n]: y

# ✓ Working directory updated!
```

## How to Use

### Installation

The plugin is already in `plugins/` directory. To activate:

```bash
# Copy to project plugins
cp plugins/python_runtime.py .aicoder/plugins/

# Or install globally
mkdir -p ~/.config/aicoder-v3/plugins
cp plugins/python_runtime.py ~/.config/aicoder-v3/plugins/

# Restart AI Coder
python3 main.py
```

### Basic Usage

```bash
# Enable the feature
/python_runtime on

# Check status
/python_runtime status

# Disable when done
/python_runtime off
```

### Example Code Executions

**Update Working Directory:**
```python
app.input_handler.cwd = "/new/path"
```

**Debug State:**
```python
print(f"Messages: {len(app.message_history.get_messages())}")
print(f"CWD: {app.input_handler.cwd}")
print(f"Tokens: {app.stats.tokens_sent}")
```

**Modify System Prompt:**
```python
messages = app.message_history.get_messages()
for msg in messages:
    if msg['role'] == 'system':
        msg['content'] = "You are now in debug mode"
```

**List Tools:**
```python
for name, tool in app.tool_manager.tools.items():
    print(f"{name}: {tool.get('auto_approved', False)}")
```

## Testing

Both unit tests and integration tests have passed:

### Unit Tests
- Plugin loading
- Tool registration
- Command registration
- Disabled state handling
- Enable/disable functionality
- Format arguments (approval display)

### Integration Tests
- Real AI Coder component integration
- Plugin context access
- Tool execution with real components
- Command handler with real context

## Safety Warnings

⚠️ **Important**: This feature gives AI full access to AI Coder's process.

**When enabled, AI can:**
- Modify any internal state
- Corrupt sessions
- Remove safety guards
- Cause crashes
- Execute arbitrary code

**Recommended for:**
- Trusted AI models
- Development and debugging
- Advanced users who understand the risks
- Situations where you need quick fixes without restarting

**NOT recommended for:**
- Untrusted AI models
- Production environments
- Systems with sensitive data
- Automated workflows without supervision

## File Structure

```
plugins/
└── python_runtime.py          # Plugin implementation (206 lines)

docs/
└── PYTHON_RUNTIME.md          # Full documentation (307 lines)
```

## Next Steps

You can now:

1. **Try it out**: Run AI Coder with the plugin enabled
2. **Read the docs**: Check `docs/PYTHON_RUNTIME.md` for full details
3. **Test safely**: Start with simple inspection commands
4. **Enable when needed**: Only turn it on when you want the AI to use it
5. **Disable when done**: Turn it off to prevent accidental use

## Example Session

```
$ python3 main.py
[+] Loaded plugin: python_runtime.py
  - run_inline_python tool
  - /python_runtime command

$ /python_runtime on
[*] Runtime Python ENABLED
    AI can now use run_inline_python tool (each execution requires approval)

> Update the working directory to /home/user/myproject

# AI will use the tool...
[*] Tool: run_inline_python
Runtime Python: ENABLED

Available in code:
  app  - AICoder instance (full access to all components)
  ctx  - PluginContext instance
  print - print function

Code to execute:
app.input_handler.cwd = "/home/user/myproject"
print("Working directory updated")

Approve [Y/n]: y
✓ Code executed successfully
```

## Implementation Details

### Architecture

The plugin follows AI Coder's plugin pattern:

```python
def create_plugin(ctx):
    """
    ctx.app provides access to all AI Coder components:
    - app.message_history
    - app.tool_manager
    - app.input_handler
    - app.plugin_system
    - etc.
    """
    # State in closure
    _state = {"enabled": False, "ctx": ctx}

    # Register tool (never auto-approved)
    ctx.register_tool(name, fn, description, parameters, auto_approved=False)

    # Register command
    ctx.register_command(name, handler, description)

    return None  # No cleanup needed
```

### Code Execution

Uses Python's `exec()` with a controlled namespace:

```python
execution_globals = {
    "app": ctx.app,
    "ctx": ctx,
    "print": print,
    "__name__": "__runtime__",
}

exec(code, execution_globals)

# Collect new variables for output
```

### State Management

Simple closure-based state:

```python
_state = {
    "enabled": False,  # Starts disabled
    "ctx": ctx         # Reference to plugin context
}
```

No complex classes or persistence - just pure closure state.

## Success Criteria - All Met ✓

- [x] Plugin that can be installed
- [x] Tool for AI to run Python code (`run_inline_python`)
- [x] Command to enable/disable feature (`/python_runtime`)
- [x] Access to full AI Coder context (via `app`)
- [x] User approval required for each execution
- [x] Starts disabled by default
- [x] Clear warnings and safety indicators
- [x] Comprehensive documentation
- [x] All tests passing
- [x] Solves the original use case (moving sessions)

## Conclusion

The Python Runtime Plugin is fully implemented, tested, and documented. It provides a powerful but safe way for AI to introspect and modify AI Coder at runtime, exactly addressing your need to update working directories and perform other runtime modifications without manual editing.

**Ready to use! 🚀**
