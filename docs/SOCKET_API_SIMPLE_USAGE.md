# Socket API - Simple Usage

## Quick Start

```bash
# Start AI Coder (creates socket automatically)
python -m aicoder

# In another terminal, find and use socket
SOCKET=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)

# Send commands
echo "is_processing" | nc -U "$SOCKET"
echo "stop" | nc -U "$SOCKET"
echo "stats" | nc -U "$SOCKET"
```

## Finding the Socket

```bash
# List all AI Coder sockets
ls -la $TMPDIR/aicoder-*.socket

# Get most recent
ls -t $TMPDIR/aicoder-*.socket | head -1
```

## Socket Path Format

```
$TMPDIR/aicoder-<pid>-<tmux_pane_or_0>.socket
```

- `$TMPDIR` - Uses `TMPDIR` env var, or `/tmp` if not set
- `<pid>` - Process ID
- `<tmux_pane_or_0>` - TMUX pane ID if in tmux, otherwise `0`

## Commands

### Quick Check
```bash
echo "is_processing" | nc -U "$SOCKET"
```

### Stop Processing
```bash
echo "stop" | nc -U "$SOCKET"
```

### Get Statistics
```bash
echo "stats" | nc -U "$SOCKET"
```

### Save Session
```bash
echo "save ~/backup.json" | nc -U "$SOCKET"
```

### Toggle YOLO Mode
```bash
# Check status
echo "yolo status" | nc -U "$SOCKET"

# Enable
echo "yolo on" | nc -U "$SOCKET"

# Disable
echo "yolo off" | nc -U "$SOCKET"
```

### Inject Message
```bash
echo "inject list all files" | nc -U "$SOCKET"
```

### Inject Multiline Text (base64)
```bash
echo "inject-text $(printf 'Line 1\nLine 2\nLine 3' | base64 -w0)" | nc -U "$SOCKET"
```

## All Commands

| Command | Description |
|---------|-------------|
| `is_processing` | Check if AI is busy |
| `status` | Get full status |
| `stats` | Get statistics |
| `yolo [on\|off\|status]` | Control YOLO mode |
| `detail [on\|off\|status]` | Control detail mode |
| `sandbox [on\|off\|status]` | Control sandbox |
| `stop` | Stop current processing |
| `retry` | Retry last request |
| `messages [count]` | List or count messages |
| `inject <msg>` | Inject user message |
| `inject-text <base64>` | Inject base64-encoded text (multiline) |
| `save [path]` | Save session |
| `reset` | Reset conversation |
| `compact [%]` | Compact memory |
| `quit` | Exit AI Coder |
| `ping` | Health check |
| `version` | Version info |
| `help` | List commands |

## TMUX Integration

```bash
# Add to ~/.tmux.conf

# Stop AI (Ctrl+A Space)
bind-key Space run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    [ -n "$socket" ] && echo "stop" | nc -U "$socket" 2>/dev/null
'

# Toggle YOLO (Ctrl+A Y)
bind-key Y run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        current=$(echo "yolo status" | nc -U "$socket" 2>/dev/null)
        if echo "$current" | grep -q "true"; then
            echo "yolo off" | nc -U "$socket" 2>/dev/null
        else
            echo "yolo on" | nc -U "$socket" 2>/dev/null
        fi
    fi
'

# Show status (Ctrl+A i)
bind-key i run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    [ -n "$socket" ] && echo "status" | nc -U "$socket" 2>/dev/null | tmux display-message
'
```

## Response Format

- **Success:** `OK` or `OK: message`
- **Data:** JSON object
- **Error:** `ERROR: message`

## Examples

```bash
# Check if busy
echo "is_processing" | nc -U "$SOCKET"
# {"processing": false}

# Stop if busy
echo "stop" | nc -U "$SOCKET"
# OK

# Get message count
echo "messages count" | nc -U "$SOCKET"
# {"total": 25, "user": 8, "assistant": 9, "system": 1, "tool": 7}

# Save with timestamp
echo "save ~/backups/aicoder-$(date +%Y%m%d-%H%M%S).json" | nc -U "$SOCKET"
# OK: Saved to ~/backups/aicoder-20250126-123456.json
```

## Troubleshooting

**Socket not found:**
- Make sure AI Coder is running
- Check `$TMPDIR/aicoder-*.socket`

**Connection refused:**
- Check socket exists: `ls -la $TMPDIR/aicoder-*.socket`
- Verify AI Coder is still running

**Timeout:**
- AI might be busy: check with `is_processing`
- Try a shorter command first: `ping`

---

**That's it! Simple, Unix-style IPC using netcat.**
