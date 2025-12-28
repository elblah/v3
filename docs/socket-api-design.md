# AI Coder Socket API - Simple Design

## Overview

Simple Unix domain socket for controlling AI Coder from external scripts.
Inspired by mpv's IPC: minimal, straightforward, practical.

## Socket Path

```
$TMPDIR/aicoder-<pid>-<tmux_pane_or_0>.socket
```

- Simple and predictable
- Always in /tmp for easy discovery
- Includes TMUX_PANE env var if running in tmux, otherwise `0`

## Finding the Socket

```bash
# Find your specific socket (if you know the PID and pane)
ls $TMPDIR/aicoder-12345-%1.socket

# Find all sockets
ls $TMPDIR/aicoder-*.socket

# Or get the most recent one
ls -t $TMPDIR/aicoder-*.socket | head -1
```

## Commands

All commands are simple text lines: `command [args...]`

Responses are either:
- `OK` for success
- `OK: message` for success with info
- `ERROR: message` for errors
- JSON for data queries

### Query Commands

#### `is_processing`
```
is_processing
```
Response (JSON):
```json
{"processing": false}
```

#### `yolo [on|off|status]`
```
yolo
yolo status
```
Response (JSON):
```json
{"enabled": true}
```

```
yolo on
```
Response: `OK`

```
yolo off
```
Response: `OK`

#### `detail [on|off|status]`
Same pattern as yolo.

#### `sandbox [on|off|status]`
Same pattern as yolo.

#### `stats`
```
stats
```
Response (JSON):
```json
{
  "messages_sent": 15,
  "api_requests": 15,
  "current_prompt_size": 45230
}
```

#### `status`
```
status
```
Returns all status info (JSON):
```json
{
  "processing": false,
  "yolo_enabled": true,
  "detail_enabled": false,
  "sandbox_enabled": true,
  "messages": 25
}
```

### Control Commands

#### `stop`
```
stop
```
Response: `OK`

Interrupts current AI processing.

#### `retry`
```
retry
```
Response: `OK`

Retry the last request.

### Message Commands

#### `messages [count]`
```
messages
```
Response (JSON list of all messages):
```json
[
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]
```

```
messages count
```
Response (JSON):
```json
{"total": 25, "user": 8, "assistant": 9, "system": 1, "tool": 7}
```

#### `inject <text>`
```
inject help me write a function
```
Response: `OK`

Inject a user message into the conversation.

### Session Commands

#### `save [path]`
```
save
```
Response: `OK: Saved to ~/.aicoder/session-20250126-123456.json`

```
save /path/to/file.json
```
Response: `OK: Saved to /path/to/file.json`

#### `reset`
```
reset
```
Response: `OK`

Clear conversation history.

#### `compact [percentage]`
```
compact
```
Response: `OK`

Compact memory using default percentage.

```
compact 50
```
Response (JSON):
```json
{"messages_before": 45, "messages_after": 23}
```

### System Commands

#### `quit`
```
quit
```
Response: `OK`

Exit AI Coder.

#### `ping`
```
ping
```
Response: `pong`

Health check.

#### `version`
```
version
```
Response (JSON):
```json
{"version": "3.0.0", "python": "3.13.5"}
```

#### `help`
```
help
```
Response:
```
Commands: is_processing, yolo, detail, sandbox, stats, status,
          stop, retry, messages, inject, inject-text, save, reset, compact,
          quit, ping, version, help
```

## Examples

### Check if AI is busy
```bash
echo "is_processing" | nc -U $TMPDIR/aicoder-12345-%1.socket
# {"processing": false}
```

### Stop current operation from tmux
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

### Toggle YOLO
```bash
echo "yolo on" | nc -U $TMPDIR/aicoder-12345-%1.socket
# OK
```

## Error Format

All errors start with `ERROR:`

```
ERROR: Not currently processing
ERROR: Unknown command: foo
ERROR: Missing argument: path
```

## Protocol

1. Connect to socket
2. Send command line + `\n`
3. Read response line + `\n`
4. Close connection

Simple request-response. No persistent connections needed.
