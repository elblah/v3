# TMUX Integration - Quick Reference

## What You Got

Three scripts that integrate AI Coder with TMUX:

| Script | Purpose |
|--------|---------|
| `tmux-popup-menu.sh` | Interactive menu with dynamic status |
| `tmux-helper.sh` | Execute single commands |
| `tmux-status.sh` | Status bar indicator |

## Quick Setup (5 minutes)

### 1. Scripts are already executable
```bash
ls -la /home/blah/poc/aicoder/v3/examples/tmux-*.sh
# Should show -rwxr-xr-x permissions
```

### 2. Add this to ~/.tmux.conf

```bash
# ==================================================
# AI Coder Integration
# ==================================================

AICODER_DIR="/home/blah/poc/aicoder/v3/examples"

# Main menu (Ctrl+A a)
bind-key a run-shell -b "$AICODER_DIR/tmux-popup-menu.sh"

# Quick actions
bind-key s run-shell -b "$AICODER_DIR/tmux-helper.sh stop"
bind-key y run-shell -b "$AICODER_DIR/tmux-helper.sh 'yolo toggle'"
bind-key d run-shell -b "$AICODER_DIR/tmux-helper.sh 'detail toggle'"
bind-key b run-shell -b "$AICODER_DIR/tmux-helper.sh 'sandbox toggle'"
bind-key S run-shell -b "$AICODER_DIR/tmux-helper.sh save"
bind-key i run-shell -b "$AICODER_DIR/tmux-helper.sh status"
bind-key c run-shell -b "$AICODER_DIR/tmux-helper.sh compact"
bind-key r run-shell -b "$AICODER_DIR/tmux-helper.sh retry"
bind-key R run-shell -b "$AICODER_DIR/tmux-helper.sh reset"
```

### 3. Reload TMUX

```bash
tmux source-file ~/.tmux.conf
```

### 4. Start AI Coder

```bash
python -m aicoder
```

### 5. Press `Ctrl+A a` to open the menu!

## Menu Preview

When you press `Ctrl+A a`, you'll see:

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

**Note**: The `[ON]/[OFF]` indicators update dynamically based on current state!

## Key Bindings

| Key | Action | Result Shows In |
|-----|--------|-----------------|
| `Ctrl+A a` | Open popup menu | Popup window |
| `Ctrl+A s` | Stop processing | Status bar (2s) |
| `Ctrl+A y` | Toggle YOLO | Status bar (3s) |
| `Ctrl+A d` | Toggle Detail | Status bar (3s) |
| `Ctrl+A b` | Toggle Sandbox | Status bar (3s) |
| `Ctrl+A S` | Save session | Status bar (3s) |
| `Ctrl+A i` | Show status | Status bar (6s) |
| `Ctrl+A c` | Compact memory | Status bar (3s) |
| `Ctrl+A r` | Retry request | Status bar (3s) |
| `Ctrl+A R` | Reset conversation | Status bar (2s) |

## How It Works

### Socket Discovery (Automatic)

1. **Exact match**: `aicoder-<pid>-<pane_id>-<random>.socket`
2. **Fallback**: Most recent `aicoder-*.socket`

Result: Each pane controls its own AI Coder instance!

### Status Display

- **Menu items**: Show `[ON]` or `[OFF]` dynamically
- **Status bar**: Shows results briefly (2-6 seconds)
- **Errors**: Displayed for 5 seconds with "ERROR:" prefix

### JSON Parsing (Fast!)

Uses `gojq` if available (much faster than jq), falls back to `jq` or `grep`.

## Testing

### Test 1: Verify Socket

```bash
# In a pane running AI Coder
echo $TMUX_PANE
ls -la /tmp/aicoder-*${TMUX_PANE#%}*.socket
```

### Test 2: Test Command

```bash
SOCKET=$(ls -t /tmp/aicoder-*.socket | head -1)
echo "status" | nc -U "$SOCKET"
```

### Test 3: Test TMUX Display

```bash
tmux display-message -d 3000 "Test: This works!"
```

### Test 4: Test Popup

```bash
tmux display-popup -E -w 40% -h 30% 'echo "Popup works!"'
```

## Common Issues

### "No AI Coder session found"

**Fix**: Make sure AI Coder is running in the current pane.

### "nc: command not found"

**Fix**: Install netcat:
```bash
# Debian/Ubuntu
sudo apt install netcat-openbsd

# Arch
sudo pacman -S netcat
```

### Popup doesn't appear

**Fix**: Check tmux version (needs 3.2+):
```bash
tmux -V
```

Use single-key shortcuts if older tmux.

### Key conflicts

**Fix**: Change key in `~/.tmux.conf`:
```bash
# Change 'a' to 'M' (Shift+m)
bind-key M run-shell -b "$AICODER_DIR/tmux-popup-menu.sh"
```

## Bonus: Status Bar Indicator

Add to `~/.tmux.conf`:

```bash
set -g status-right '%H:%M %Y-%m-%d | #(/home/blah/poc/aicoder/v3/examples/tmux-status.sh)'
```

Result: Status bar shows `AI:Running` (red) or `AI:Ready` (green).

## Full Documentation

See `TMUX_SETUP.md` for complete documentation.

## What Makes This Cool

1. **Pane-aware**: Each pane controls its own AI Coder instance
2. **Dynamic status**: Menu shows actual current state
3. **Fast**: Uses `gojq` for quick JSON parsing
4. **No code changes**: Pure external integration
5. **Clean**: Commands don't need to know about tmux
6. **Discoverable**: Menu shows all options

Enjoy!
