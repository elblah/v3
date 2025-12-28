# TMUX Integration for AI Coder

This document describes how to set up TMUX integration with AI Coder for quick control via key bindings and an interactive popup menu.

## Quick Start

1. Make the scripts executable:
   ```bash
   chmod +x /home/blah/poc/aicoder/v3/examples/tmux-popup-menu.sh
   chmod +x /home/blah/poc/aicoder/v3/examples/tmux-helper.sh
   ```

2. Add the bindings to your `~/.tmux.conf` (see below).

3. Reload tmux configuration:
   ```bash
   tmux source-file ~/.tmux.conf
   ```

4. Start AI Coder in a tmux pane.

5. Press `Ctrl+A a` to open the popup menu.

## Features

### Popup Menu with Dynamic Status

The popup menu shows the current state of toggle options:

```
AI Coder Control Menu - Pane: %1

Status: Idle | Messages: 25

=== Toggle Options ===
y) Toggle YOLO Mode       [ON]
d) Toggle Detail Mode     [OFF]
s) Toggle Sandbox         [ON]

=== Actions ===
1) Stop Processing
2) Save Session
3) Show Statistics
4) Show Full Status
5) Compact Memory (50%)
6) Reset Conversation
7) Retry Last Request

0) Cancel
```

**Key Features:**
- **Pane-aware**: Finds the socket for the current pane
- **Status display**: Shows current state of YOLO, Detail, Sandbox modes
- **No socket found**: Displays error message if no AI Coder session
- **gojq support**: Uses gojq for fast JSON parsing (falls back to jq or grep)
- **Clean UI**: Uses tmux popup for non-intrusive interaction

### Single-Key Shortcuts

Quick access to common actions:

| Key | Action | Display Duration |
|-----|--------|------------------|
| `Ctrl+A s` | Stop processing | 2s |
| `Ctrl+A y` | Toggle YOLO mode | 3s |
| `Ctrl+A d` | Toggle Detail mode | 3s |
| `Ctrl+A S` | Save session | 3s |
| `Ctrl+A i` | Show status | 6s |
| `Ctrl+A c` | Compact memory | 3s |
| `Ctrl+A r` | Retry request | 3s |
| `Ctrl+A R` | Reset conversation | 2s |

## Configuration

### Step 1: Add to ~/.tmux.conf

Add the following to your `~/.tmux.conf`:

```bash
# ==================================================
# AI Coder Integration
# ==================================================

# Set the path to the scripts
AICODER_DIR="/home/blah/poc/aicoder/v3/examples"

# ==================================================
# Main Popup Menu
# ==================================================

# Open AI Coder control menu (Ctrl+A a)
bind-key a run-shell -b "$AICODER_DIR/tmux-popup-menu.sh"

# Alternative: Use Ctrl+A A for menu
bind-key A run-shell -b "$AICODER_DIR/tmux-popup-menu.sh"

# ==================================================
# Quick Actions
# ==================================================

# Stop processing (Ctrl+A s)
bind-key s run-shell -b "$AICODER_DIR/tmux-helper.sh stop"

# Toggle YOLO mode (Ctrl+A y)
bind-key y run-shell -b "$AICODER_DIR/tmux-helper.sh 'yolo toggle'"

# Toggle Detail mode (Ctrl+A d)
bind-key d run-shell -b "$AICODER_DIR/tmux-helper.sh 'detail toggle'"

# Toggle Sandbox (Ctrl+A b)
bind-key b run-shell -b "$AICODER_DIR/tmux-helper.sh 'sandbox toggle'"

# ==================================================
# Session Management
# ==================================================

# Save session (Ctrl+A S)
bind-key S run-shell -b "$AICODER_DIR/tmux-helper.sh save"

# Compact memory (Ctrl+A c)
bind-key c run-shell -b "$AICODER_DIR/tmux-helper.sh compact"

# Reset conversation (Ctrl+A R)
bind-key R run-shell -b "$AICODER_DIR/tmux-helper.sh reset"

# Retry last request (Ctrl+A r)
bind-key r run-shell -b "$AICODER_DIR/tmux-helper.sh retry"

# ==================================================
# Information Display
# ==================================================

# Show full status (Ctrl+A i)
bind-key i run-shell -b "$AICODER_DIR/tmux-helper.sh status"

# Show statistics (Ctrl+A I)
bind-key I run-shell -b "$AICODER_DIR/tmux-helper.sh stats"

# ==================================================
# Custom Command Input
# ==================================================

# Type custom command (Ctrl+A :)
bind-key : command-prompt -p "AI Coder command: " "
    AICODER_DIR=\"$AICODER_DIR\"
    RESP=\$(echo \"%1\" | \$AICODER_DIR/tmux-helper.sh 2>&1 | grep -o \"AI Coder: .*\" || echo \"Sent: %1\")
    tmux display-message -d 3000 \"\$RESP\"
"
```

### Step 2: Reload Configuration

```bash
tmux source-file ~/.tmux.conf
```

Or just restart tmux.

## How It Works

### Socket Discovery

The scripts find the correct socket for the current pane:

1. **Exact match**: Looks for `aicoder-<pid>-<pane_id>-<random>.socket`
2. **Fallback**: Uses the most recent `aicoder-*.socket` if no exact match

This means:
- Multiple AI Coder instances can run in different panes
- Each pane controls its own instance
- Works even without `TMUX_PANE` environment variable

### JSON Parsing

The scripts use `gojq` (preferred), `jq`, or `grep` fallback for parsing JSON responses:

```bash
# Preferred: gojq (fast)
gojq -r '.data.message'

# Fallback: jq
jq -r '.data.message'

# Last resort: grep
grep -o '"message":"[^"]*"' | cut -d'"' -f4
```

### Error Handling

The scripts handle various error conditions:

- **No socket found**: Displays error in tmux status bar
- **Invalid socket**: Shows path validation error
- **Command errors**: Extracts error message from JSON response
- **No response**: Displays timeout message

## Testing

### Test 1: Verify Scripts Are Executable

```bash
ls -la /home/blah/poc/aicoder/v3/examples/tmux-*.sh
```

### Test 2: Find Socket for Current Pane

```bash
# In a pane running AI Coder
echo "Pane ID: $TMUX_PANE"
ls -t /tmp/aicoder-*${TMUX_PANE#%}*.socket | head -1
```

### Test 3: Test Direct Command Execution

```bash
# Find socket
SOCKET=$(ls -t /tmp/aicoder-*.socket | head -1)

# Test status command
echo "status" | nc -U "$SOCKET"

# Test toggle command
echo "yolo status" | nc -U "$SOCKET"
```

### Test 4: Test TMUX Display

```bash
# This should show a message for 3 seconds
tmux display-message -d 3000 "Test: This should appear briefly"
```

### Test 5: Test Popup Menu

```bash
# Test popup directly
tmux display-popup -E -w 40% -h 30% 'echo "Test popup"'
```

## Troubleshooting

### "No AI Coder session found"

**Cause**: No socket file exists for current pane.

**Solutions**:
1. Ensure AI Coder is running in the current pane
2. Check that socket file exists: `ls -la /tmp/aicoder-*.socket`
3. Check pane ID: `echo $TMUX_PANE`
4. Try the popup menu in a different pane where AI Coder is running

### "nc: command not found"

**Cause**: `netcat` not installed.

**Solution**:
```bash
# On Debian/Ubuntu
sudo apt install netcat-openbsd

# On Arch
sudo pacman -S netcat

# On Fedora
sudo dnf install nc
```

### "gojq: command not found"

**Cause**: `gojq` not installed.

**Solution**:
```bash
# Install gojq (Go-based jq, much faster)
# Check your package manager or install from source:
# https://github.com/itchyny/gojq

# Or install jq as fallback
# On Debian/Ubuntu
sudo apt install jq

# On Arch
sudo pacman -S jq
```

### Popup menu doesn't appear

**Cause**: tmux version doesn't support `display-popup` (requires tmux 3.2+).

**Solution**: Check tmux version:
```bash
tmux -V
```

If older than 3.2, use the single-key shortcuts instead, or upgrade tmux.

### Key bindings conflict

**Cause**: Key already bound to something else.

**Solution**: Use different key bindings in `~/.tmux.conf`:
```bash
# Change 'a' to something else like 'M' (Shift+m)
bind-key M run-shell -b "$AICODER_DIR/tmux-popup-menu.sh"
```

## Advanced Usage

### Custom Menu Actions

To add custom actions, edit `tmux-popup-menu.sh` and add new cases:

```bash
# In execute_action function, add:
[8]*)
    cmd="custom_command"
    display_msg="Custom action executed"
    ;;
```

### Status Bar Integration

Show AI Coder status in tmux status line:

Add to `~/.tmux.conf`:
```bash
# AI Coder status indicator
set -g status-right '#{?pane_synchronized,,} %H:%M %Y-%m-%d | #(/home/blah/poc/aicoder/v3/examples/tmux-status.sh)'
```

Create `tmux-status.sh`:
```bash
#!/bin/bash
SOCKET=$(ls -t /tmp/aicoder-${TMUX_PANE#%}*.socket 2>/dev/null | head -1)
if [ -n "$SOCKET" ]; then
    STATUS=$(echo "status" | nc -U "$SOCKET" 2>/dev/null)
    if echo "$STATUS" | grep -q '"processing":true'; then
        echo "#[fg=red]AI:Running#[fg=default]"
    else
        echo "#[fg=green]AI:Ready#[fg=default]"
    fi
fi
```

### Multiple AI Coder Sessions

The scripts automatically handle multiple sessions by:
- Matching socket to current pane ID
- Falling back to most recent socket if no match
- Controlling the correct instance

No special configuration needed!

## Files

| File | Purpose |
|------|---------|
| `tmux-popup-menu.sh` | Interactive menu with dynamic status |
| `tmux-helper.sh` | Execute single commands |
| `tmux-integration.sh` | Legacy key bindings (still works) |
| `TMUX_SETUP.md` | This file |

## Requirements

- **tmux**: Version 3.2+ for popup menu support
- **netcat (nc)**: For socket communication
- **gojq** (optional): Fast JSON parsing
- **jq** (optional): JSON parsing fallback
- **bash**: For shell script execution

## Contributing

To add new features:

1. Update the relevant script (`tmux-popup-menu.sh` or `tmux-helper.sh`)
2. Update this documentation
3. Test with multiple panes/sessions
4. Verify error handling

## License

Same as AI Coder project.
