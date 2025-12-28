# TMUX Integration - Implementation Summary

## What Was Implemented

### 1. Enhanced Socket Server with Toggle Support

**File Modified:** `aicoder/core/socket_server.py`

**Changes:**
- Added `toggle` option to `yolo` command
- Added `toggle` option to `detail` command
- Added `toggle` option to `sandbox` command
- Updated help command to document toggle options

**New Commands:**
```bash
yolo toggle    # Toggle YOLO mode on/off
detail toggle  # Toggle detail mode on/off
sandbox toggle # Toggle sandbox on/off
```

**Response Format:**
```json
{
  "enabled": true,
  "message": "YOLO enabled"
}
```

### 2. Popup Menu Script

**File Created:** `examples/tmux-popup-menu.sh`

**Features:**
- Interactive popup menu with tmux `display-popup`
- Dynamic status display (shows [ON] or [OFF] for toggles)
- Pane-aware socket discovery
- Error handling (no socket found, invalid commands)
- `gojq` support for fast JSON parsing (falls back to jq/grep)
- Non-intrusive feedback (disappears after 2-6 seconds)

**Menu Options:**
```
y) Toggle YOLO Mode       [ON/OFF]
d) Toggle Detail Mode     [ON/OFF]
s) Toggle Sandbox         [ON/OFF]
1) Stop Processing
2) Save Session
3) Show Statistics
4) Show Full Status
5) Compact Memory (50%)
6) Reset Conversation
7) Retry Last Request
0) Cancel
```

### 3. Helper Script for Single Commands

**File Created:** `examples/tmux-helper.sh`

**Purpose:** Execute single commands without opening menu

**Usage:**
```bash
tmux-helper.sh stop
tmux-helper.sh "yolo toggle"
tmux-helper.sh status
```

**Features:**
- Displays result in tmux status bar
- Error handling with clear messages
- Socket discovery for current pane

### 4. Status Bar Indicator

**File Created:** `examples/tmux-status.sh`

**Purpose:** Show AI Coder status in tmux status line

**Features:**
- Shows `AI:Running` (red) when processing
- Shows `AI:Ready` (green) when idle
- Pane-aware
- Non-intrusive

### 5. Documentation

**Files Created:**
- `examples/TMUX_SETUP.md` - Complete setup guide
- `examples/TMUX_QUICKREF.md` - Quick reference card

**Files Updated:**
- `README.md` - Added TMUX integration section
- `docs/SOCKET_API.md` - Documented toggle commands

## How to Configure

### Quick Setup (2 minutes)

Add this to `~/.tmux.conf`:

```bash
# AI Coder Integration
AICODER_DIR="/home/blah/poc/aicoder/v3/examples"

# Main menu (Ctrl+A a)
bind-key a run-shell -b "$AICODER_DIR/tmux-popup-menu.sh"

# Quick actions
bind-key s run-shell -b "$AICODER_DIR/tmux-helper.sh stop"
bind-key y run-shell -b "$AICODER_DIR/tmux-helper.sh 'yolo toggle'"
bind-key d run-shell -b "$AICODER_DIR/tmux-helper.sh 'detail toggle'"
bind-key S run-shell -b "$AICODER_DIR/tmux-helper.sh save"
bind-key i run-shell -b "$AICODER_DIR/tmux-helper.sh status"
```

Reload tmux:
```bash
tmux source-file ~/.tmux.conf
```

## How It Works

### Architecture

```
User Presses Key
     ↓
tmux binds to key
     ↓
Calls script (tmux-popup-menu.sh or tmux-helper.sh)
     ↓
Script finds socket for current pane
     ↓
Script sends command to socket
     ↓
Socket server executes command
     ↓
Socket returns JSON response
     ↓
Script parses JSON (gojq → jq → grep)
     ↓
Script displays result in tmux status bar
```

### Socket Discovery

1. **Exact match**: `aicoder-<pid>-<pane_id>-<random>.socket`
2. **Fallback**: Most recent `aicoder-*.socket`

This ensures:
- Multiple AI Coder instances can run in different panes
- Each pane controls its own instance
- Works even without `TMUX_PANE` environment variable

### Status Display

- **Menu items**: Show actual current state `[ON]` or `[OFF]`
- **Status bar**: Shows results briefly (2-6 seconds)
- **Errors**: Displayed with "ERROR:" prefix for 5 seconds

## Benefits

1. **No Architectural Changes**: Socket API remains pure machine interface
2. **Clean Separation**: Display logic in tmux, command logic in server
3. **Better UX**: Discoverable menus, non-intrusive status bar
4. **Fast**: Uses `gojq` for JSON parsing
5. **Extensible**: Easy to add new menu items
6. **Testable**: Scripts can be tested independently

## Testing

### Test 1: Toggle Commands Work

```bash
# Start AI Coder
python -m aicoder

# In another terminal:
SOCKET=$(ls -t /tmp/aicoder-*.socket | head -1)

# Test toggle
echo "yolo status" | nc -U "$SOCKET"   # Check current state
echo "yolo toggle" | nc -U "$SOCKET"   # Toggle
echo "yolo status" | nc -U "$SOCKET"   # Verify change
```

### Test 2: Scripts Are Executable

```bash
ls -la /home/blah/poc/aicoder/v3/examples/tmux-*.sh
# Should show -rwxr-xr-x permissions
```

### Test 3: TMUX Display

```bash
tmux display-message -d 3000 "Test: This works!"
```

### Test 4: Popup Menu

```bash
tmux display-popup -E -w 40% -h 30% 'echo "Popup works!"'
```

## Requirements

- **tmux**: Version 3.2+ for popup menu
- **netcat (nc)**: For socket communication
- **gojq** (optional): Fast JSON parsing
- **jq** (optional): JSON parsing fallback
- **bash**: For shell script execution

## Troubleshooting

### "No AI Coder session found"

Make sure AI Coder is running in the current pane.

### "nc: command not found"

Install netcat:
```bash
sudo apt install netcat-openbsd  # Debian/Ubuntu
sudo pacman -S netcat           # Arch
```

### "gojq: command not found"

Install gojq or jq:
```bash
# gojq (fast, recommended)
# https://github.com/itchyny/gojq

# jq (fallback)
sudo apt install jq  # Debian/Ubuntu
sudo pacman -S jq    # Arch
```

### Popup doesn't appear

Check tmux version (needs 3.2+):
```bash
tmux -V
```

Use single-key shortcuts if older tmux.

## File Structure

```
/home/blah/poc/aicoder/v3/
├── aicoder/core/
│   └── socket_server.py          # Modified: added toggle support
├── docs/
│   └── SOCKET_API.md             # Modified: documented toggle
├── examples/
│   ├── tmux-popup-menu.sh        # Created: interactive menu
│   ├── tmux-helper.sh            # Created: single commands
│   ├── tmux-status.sh           # Created: status bar
│   ├── TMUX_SETUP.md             # Created: full setup guide
│   ├── TMUX_QUICKREF.md         # Created: quick reference
│   └── tmux-integration.sh      # Existing: legacy bindings
└── README.md                    # Modified: added TMUX section
```

## Next Steps (Optional Enhancements)

1. **Status Bar Integration**: Add to tmux status line
2. **Custom Actions**: Add more menu options
3. **Keyboard Navigation**: Use arrow keys in menu
4. **History**: Show recent commands
5. **Multiple Sessions**: Enhance for multiple AI Coder instances

## Design Decisions

### Why External Scripts Instead of Screen Output

1. **Clean Architecture**: Socket API stays machine-focused
2. **Separation of Concerns**: Display logic in tmux, not in Python code
3. **Flexibility**: Easy to modify without touching core code
4. **Testing**: Scripts can be tested independently
5. **Performance**: No overhead of redirecting stdout

### Why Toggle Instead of On/Off in Scripts

1. **Simpler Scripts**: No need to query current state first
2. **Better UX**: One key press toggles, shows new state
3. **Less Network**: Single command instead of status + toggle
4. **Consistent**: Matches common UI patterns

### Why gojq

1. **Performance**: Much faster than jq for JSON parsing
2. **Binary**: No dependency on jq installation
3. **Optional**: Falls back to jq or grep if not available
4. **User Preference**: You specifically use gojq on your machine

## Summary

This implementation provides:
- ✅ Interactive popup menu with dynamic status
- ✅ Quick single-key shortcuts
- ✅ Status bar integration option
- ✅ Pane-aware (multiple instances)
- ✅ Clean architecture (no code changes to commands)
- ✅ Fast JSON parsing (gojq support)
- ✅ Comprehensive documentation
- ✅ Error handling
- ✅ Toggle support for all mode commands

The solution maintains clean separation between IPC (machine interface) and UI (tmux display), while providing an excellent user experience.
