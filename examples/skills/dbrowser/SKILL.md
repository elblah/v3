---
name: dbrowser
description: >
  Browser automation via dbrowser Unix socket (/run/user/1000/tmp/dbrowser.sock).
  Use for AI browsing/exploration when sites need JavaScript rendering, interactive
  features, or simple tools (curl, wget, lynx) can't access the content.

  **Scripts for users**: Use `curl`, `wget`, `lynx`, or Python `urllib` instead.
  Only use dbrowser in user scripts if explicitly requested.

  Examples needed: JavaScript execution, screenshots, cookies/sessions, interactive web apps.
  If socket not responding, ask user to start dbrowser.

**Important:** Only request screenshots if the model supports vision (vision-capable models) OR if a vision service like mmx is available. Do not take screenshots unless they can be analyzed.
---

# dbrowser (Browser via Unix Socket)

**Fallback tool** - try `curl`, `lynx -dump`, `wget` first.

Unix socket at `/run/user/1000/tmp/dbrowser.sock`. All commands:
```bash
echo '{"command": [<args>...]}' | nc -U /run/user/1000/tmp/dbrowser.sock
```

## Refresh Command Reference

To update knowledge of dbrowser commands:
```bash
echo '{"command": ["help"]}' | nc -U /run/user/1000/tmp/dbrowser.sock
```

## IPC Commands

| Command | Description |
|---------|-------------|
| `help` | Show this help |
| `load-url <url>` | Load URL |
| `eval-js <code>` | Execute JavaScript |
| `screenshot` | Return PNG as base64 |
| `back` / `forward` | Navigation |
| `status` | Current URL, title, loading state |
| `get-console-output [lines]` | Console output |
| `list-network-requests [max]` | Network requests |
| `get-network-request <id>` | Request details |
| `resize <width> <height>` | Resize window |
| `maximize` / `unmaximize` | Window state |
| `fullscreen` / `unfullscreen` | Fullscreen toggle |
| `rotate` | Swap width/height |
| `device [profile]` | Device profile |
| `set-user-agent <ua>` | Set user agent string |
| `get-user-agent` | Get current user agent |

## Examples

```bash
# Load URL
echo '{"command": ["load-url", "https://example.com"]}' | nc -U /run/user/1000/tmp/dbrowser.sock

# Take screenshot
echo '{"command": ["screenshot"]}' | nc -U /run/user/1000/tmp/dbrowser.sock

# Execute JavaScript
echo '{"command": ["eval-js", "document.title"]}' | nc -U /run/user/1000/tmp/dbrowser.sock

# Get status
echo '{"command": ["status"]}' | nc -U /run/user/1000/tmp/dbrowser.sock

# Set device profile
echo '{"command": ["device", "iPhone 12"]}' | nc -U /run/user/1000/tmp/dbrowser.sock
```
