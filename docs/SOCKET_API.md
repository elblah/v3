# AI Coder Socket API

Simple Unix domain socket API for controlling AI Coder from external scripts.
Inspired by mpv's IPC: minimal, straightforward, practical.

## Overview

The socket server provides a simple text-based protocol for:
- Querying AI Coder state (is processing, mode settings, statistics)
- Controlling AI Coder behavior (stop, retry, toggle modes)
- Managing conversation (save, reset, compact)
- Injecting messages into the conversation

## Socket Path

```
$TMPDIR/aicoder-<pid>-<tmux_pane_or_0>.socket
```

- `<pid>` - Process ID of the AI Coder instance
- `<tmux_pane_or_0>` - TMUX pane ID if `TMUX_PANE` env var is set, otherwise `0`

### Fixed Socket Path

Set `AICODER_SOCKET_IPC_FILE` to use a custom, predictable socket path:

```bash
export AICODER_SOCKET_IPC_FILE=/tmp/my-agent.socket
python -m aicoder
```

This is useful for:
- Multi-agent setups (multiple instances with known paths)
- Bash scripts that need to connect to specific agents
- Running outside of tmux

### Finding the Socket

```bash
# Find your specific socket
ls $TMPDIR/aicoder-*.socket

# Get the most recently modified socket
ls -t $TMPDIR/aicoder-*.socket | head -1
```

## Socket-Only Mode

Run AI Coder without readline input, only responding to socket commands:

```bash
export AICODER_SOCKET_ONLY=1
python -m aicoder
```

In this mode:
- No interactive input loop
- All output still goes to stdout/stderr
- Full control via socket commands
- Enables scripting and multi-agent orchestration

## Protocol

Simple request-response:
1. Connect to socket
2. Send command line + `\n`
3. Read response line + `\n`
4. Close connection

### Response Format

- **Success:** `OK` or `OK: message`
- **Data:** JSON object/array
- **Error:** `ERROR: message`

### Example Using netcat

```bash
echo "is_processing" | nc -U $TMPDIR/aicoder-12345-%1.socket
```

### Example Using Python

```python
import socket

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect("$TMPDIR/aicoder-12345-%1.socket")
sock.sendall(b"is_processing\n")
response = sock.recv(4096).decode().strip()
sock.close()
```

### Using the Helper Module

```python

# Simple command
response = send_command("$TMPDIR/aicoder-12345-%1.socket", "is_processing")

# JSON response
data = send_json("$TMPDIR/aicoder-12345-%1.socket", "stats")

# Quick helpers
is_processing("$TMPDIR/aicoder-12345-%1.socket")
stop("$TMPDIR/aicoder-12345-%1.socket")
save("$TMPDIR/aicoder-12345-%1.socket", "~/backup.json")
```

## Commands

### Query Commands

#### `is_processing`
Check if AI is currently processing a request.

```
is_processing
```

**Response (JSON):**
```json
{"processing": false}
```

#### `status`
Get full status including mode settings.

```
status
```

**Response (JSON):**
```json
{
  "processing": false,
  "yolo_enabled": true,
  "detail_enabled": false,
  "sandbox_enabled": true,
  "messages": 25
}
```

#### `stats`
Get session statistics.

```
stats
```

**Response (JSON):**
```json
{
  "messages_sent": 15,
  "messages_received": 12,
  "api_requests": 15,
  "api_success": 14,
  "api_errors": 1,
  "user_interactions": 15,
  "compactions": 2,
  "current_prompt_size": 45230
}
```

### Mode Commands

#### `yolo [on|off|status|toggle]`
Control YOLO mode (auto-approve tool actions).

```
yolo          # Show status
yolo status   # Show status
yolo on       # Enable
yolo off      # Disable
yolo toggle   # Toggle current state
```

**Response (status):**
```json
{"enabled": true}
```

**Response (on/off/toggle):**
```json
{"enabled": true, "message": "YOLO enabled"}
```

#### `detail [on|off|status|toggle]`
Control detail mode (verbose tool output).

```
detail         # Show status
detail status   # Show status
detail on      # Enable
detail off     # Disable
detail toggle   # Toggle current state
```

#### `sandbox [on|off|status|toggle]`
Control filesystem sandbox.

```
sandbox         # Show status
sandbox status  # Show status
sandbox on      # Enable
sandbox off     # Disable
sandbox toggle   # Toggle current state
```

### Control Commands

#### `stop`
Interrupt current AI processing.

```
stop
```

**Response:**
```
OK
```

#### `retry`
Retry the last AI request.

```
retry
```

**Response:**
```
OK
```

### Message Commands

#### `messages [count]`
List messages or get message count.

```
messages              # List all messages (JSON)
messages count         # Get counts by type
```

**Response (count):**
```json
{"total": 25, "user": 8, "assistant": 9, "system": 1, "tool": 7}
```

#### `inject <message>`
Inject a user message into the conversation.

```
inject help me write a function
inject list all files in /tmp
```

**Response:**
```
OK
```

#### `inject-text <base64_text>`
Inject base64-encoded text directly into the conversation. Supports multiline text and special characters.

```
inject-text SGVsbG8Kd29ybGQKZm9vCmJhcg==
```

**Shell example (multiline):**
```bash
echo "inject-text $(printf 'Line 1\nLine 2\nLine 3' | base64 -w0)" | nc -U "$SOCKET"
```

**Shell example (from file):**
```bash
echo "inject-text $(base64 -w0 myfile.txt)" | nc -U "$SOCKET"
```

**Response (success):**
```json
{"status": "success", "data": {"injected": true, "length": 42}}
```

**Response (error):**
```json
{"status": "error", "code": 1303, "message": "Invalid base64 encoding"}
```

#### `command <text>`
Execute any slash command via socket. This gives you access to all AI Coder commands except `/retry` (use `process` instead).

```
command /save ~/backup.json
command /yolo on
command /reset
command /stats
```

**Note:** Do not use `/retry` via socket - use `process` command instead.

**Response (success):**
```json
{"status": "success", "data": {"executed": "/save", "should_quit": false, "run_api_call": false}}
```

**Response (error):**
```json
{"status": "error", "code": 1301, "message": "Unknown command: /unknown"}
```

#### `process`
Trigger AI processing with current messages. Runs in background thread, returns immediately.

```
process
```

**Note:** In socket-only mode, YOLO mode is auto-enabled (auto-approve tool calls) since approval prompts won't work.

**Response (success):**
```json
{"status": "success", "data": {"processing": true, "message": "Started processing"}}
```

**Response (error - already processing):**
```json
{"status": "error", "code": 1001, "message": "Already processing, please wait"}
```

**Complete headless workflow:**
```bash
# Start in socket-only mode
AICODER_SOCKET_ONLY=1 AICODER_SOCKET_IPC_FILE=/tmp/agent.socket python -m aicoder &

# Send prompt
echo "inject-text $(echo 'List all files' | base64 -w0)" | nc -U /tmp/agent.socket

# Trigger AI processing
echo "process" | nc -U /tmp/agent.socket

# Wait for completion
while true; do
    status=$(echo "is_processing" | nc -U /tmp/agent.socket | jq -r '.processing')
    [ "$status" = "false" ] && break
    sleep 0.5
done

# Get the assistant response
echo "messages" | nc -U /tmp/agent.socket | jq -r '.messages[-1].content'
```

### Session Commands

#### `save [path]`
Save current session to file.

```
save                              # Save to default location
save ~/backup/session.json        # Save to specific path
```

**Response:**
```
OK: Saved to ~/.aicoder/session-20250126-123456.json
```

#### `reset`
Clear conversation history (keep system prompt).

```
reset
```

**Response:**
```
OK
```

#### `compact [percentage]`
Compact memory by pruning old tool results.

```
compact           # Use default (50%)
compact 30         # Prune 30% of tool results
```

**Response (JSON):**
```json
{"messages_before": 45, "messages_after": 23}
```

### System Commands

#### `quit`
Exit AI Coder.

```
quit
```

**Response:**
```
OK
```

## Examples

### Check if AI is busy
```bash
echo "is_processing" | nc -U $TMPDIR/aicoder-12345-%1.socket
# {"processing": false}
```

### Stop from tmux key binding
```bash
echo "stop" | nc -U $TMPDIR/aicoder-12345-%1.socket
# OK
```

### Save session
```bash
echo "save ~/backup/session.json" | nc -U $TMPDIR/aicoder-12345-%1.socket
# OK: Saved to ~/backup/session.json
```

### Get message count
```bash
echo "messages count" | nc -U $TMPDIR/aicoder-12345-%1.socket
# {"total": 25, "user": 8, "assistant": 9, "system": 1, "tool": 7}
```

### Inject a message
```bash
echo "inject list all files" | nc -U $TMPDIR/aicoder-12345-%1.socket
# OK
```

### Toggle YOLO mode
```bash
# Check current
echo "yolo status" | nc -U $TMPDIR/aicoder-12345-%1.socket
# {"enabled": false}

# Toggle (easiest way)
echo "yolo toggle" | nc -U $TMPDIR/aicoder-12345-%1.socket
# {"enabled": true, "message": "YOLO enabled"}

# Enable explicitly
echo "yolo on" | nc -U $TMPDIR/aicoder-12345-%1.socket
# {"enabled": true, "message": "YOLO enabled"}

# Verify
echo "yolo status" | nc -U $TMPDIR/aicoder-12345-%1.socket
# {"enabled": true}
```

### Compact memory
```bash
echo "compact 50" | nc -U $TMPDIR/aicoder-12345-%1.socket
# {"messages_before": 45, "messages_after": 23}
```

## TMUX Integration

See `examples/tmux-integration.sh` for complete tmux key bindings.

### Quick Setup

Add to `~/.tmux.conf`:

```bash
# Stop AI processing (Ctrl+A Space)
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

### Interactive Menu with fzf

```bash
# Command menu (Ctrl+A ;)
bind-key \; run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    MENU="stop:stop\nsave:save\nstatus:status\nyolo-on:yolo on\nyolo-off:yolo off\n"
    CHOICE=$(echo -e "$MENU" | fzf --prompt="AI: ")
    [ -n "$CHOICE" ] && echo "$CHOICE" | cut -d: -f2 | nc -U "$socket" 2>/dev/null
'
```

## Error Handling

All errors start with `ERROR:` prefix.

```
ERROR: Not processing
ERROR: Unknown command: foo
ERROR: Missing argument: path
ERROR: Path outside allowed directories
ERROR: Timeout
```

## Testing

Run the test script while AI Coder is running:

```bash
./tests/test_socket_server.py
```

## Files

- `aicoder/core/socket_server.py` - Socket server implementation
- `docs/socket-api-design.md` - Design documentation
- `examples/socket_example.sh` - Example usage script
- `examples/tmux-integration.sh` - TMUX key bindings
- `tests/test_socket_server.py` - Test suite

## Security

- Socket file permissions: `0600` (owner only)
- File operations respect sandbox settings
- Paths validated to prevent directory traversal
- All commands logged in debug mode

## Debug Mode

Set `DEBUG=1` to log all socket commands:

```
DEBUG=1 python -m aicoder
```

Output:
```
[Socket] Listening on $TMPDIR/aicoder-12345-%1.socket
[Socket] Cmd: is_processing
[Socket] Sent: {"processing": false}
```
