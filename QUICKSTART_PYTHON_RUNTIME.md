# Python Runtime Plugin - Quick Start

## 5-Minute Quick Start

### 1. Install the Plugin

```bash
# Copy to project plugins
mkdir -p .aicoder/plugins
cp plugins/python_runtime.py .aicoder/plugins/

# Restart AI Coder
python3 main.py
```

### 2. Enable the Feature

```
/python_runtime on
```

### 3. Use It!

Ask AI to do something:

```
> Update the working directory to /home/user/myproject
```

AI will use the `run_inline_python` tool. Approve when prompted:

```
[*] Tool: run_inline_python
Runtime Python: ENABLED
...
Code to execute:
app.input_handler.cwd = "/home/user/myproject"

Approve [Y/n]: y
```

### 4. Done!

```
✓ Code executed successfully
```

### Disable When Done

```
/python_runtime off
```

## Common Tasks

### Debug Current State

```
> Show me the current working directory and message count
```

AI will run:
```python
print(f"CWD: {app.input_handler.cwd}")
print(f"Messages: {len(app.message_history.get_messages())}")
```

### List All Tools

```
> List all available tools and whether they require approval
```

AI will run:
```python
for name, tool in app.tool_manager.tools.items():
    status = "AUTO" if tool.get('auto_approved') else "MANUAL"
    print(f"{name}: {status}")
```

### Modify System Prompt

```
> Change the system prompt to add "You are in debug mode"
```

AI will run:
```python
messages = app.message_history.get_messages()
for msg in messages:
    if msg['role'] == 'system':
        msg['content'] += "\n\nYou are in debug mode"
        break
print("System prompt updated")
```

## Safety Reminders

- ⚠️ Always review code before approving
- ⚠️ This gives AI full access to AI Coder's internals
- ✅ Disable with `/python_runtime off` when not needed
- ✅ Each execution requires approval

## Need More?

See full documentation: `docs/PYTHON_RUNTIME.md`
