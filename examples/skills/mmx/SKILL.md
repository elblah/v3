---
name: mmx
description: >
  AI assistant via mmx local Unix socket service.
  Use for web searches and image analysis via AI vision.
  Socket at /run/user/1000/tmp/mmx.sock.
  If socket not responding, ask user to start mmx-server.
---

# mmx (AI via Unix Socket)

Local Unix socket at `/run/user/1000/tmp/mmx.sock`.

**IMPORTANT: Always use timeout=300 when calling mmx via run_shell_command.** Vision commands can take 30-60+ seconds. Using the default 30s timeout will cause failures.

## Command Format

```bash
echo '{"command": [<args>...]}' | nc -U /run/user/1000/tmp/mmx.sock
```

## Refresh Command Reference

To update knowledge of mmx commands:
```bash
echo '{"command": ["help"]}' | nc -U /run/user/1000/tmp/mmx.sock
```

## IPC Commands

| Command | Description |
|---------|-------------|
| `["help"]` | Show help |
| `["search", "<query>"]` | Web search |
| `["vision", "<image-url>"]` | Describe image |
| `["vision", "<image-url>", "<prompt>"]` | Ask specific question |

## Examples

```bash
# Web search
echo '{"command": ["search", "miniMax AI news"]}' | nc -U /run/user/1000/tmp/mmx.sock

# Describe image (default prompt)
echo '{"command": ["vision", "https://example.com/photo.jpg"]}' | nc -U /run/user/1000/tmp/mmx.sock

# Ask specific question about image
echo '{"command": ["vision", "https://example.com/photo.jpg", "What breed is this?"]}' | nc -U /run/user/1000/tmp/mmx.sock

# Local file (validated with 'file' command)
echo '{"command": ["vision", "/path/to/local/image.png"]}' | nc -U /run/user/1000/tmp/mmx.sock
```

## Notes

- Token is read from `~/.mmx/config.json`
- image can be URL or local file path
- prompt is optional, defaults to "Describe the image."

## File Paths for Vision Analysis

**IMPORTANT:** When using local file paths for vision analysis, save files to the current working directory or project root, NOT `/tmp`.

The sandbox `/tmp` is not shared between the AI and mmx. Files saved to `/tmp` will not be accessible to mmx.

```bash
# Use absolute path from current directory:
# /home/user/project/screenshot.png  (good - mmx can access)
# /tmp/screenshot.png                 (bad - mmx cannot access)
```

## Timeout for Vision Commands

Vision commands can take 30-60+ seconds. Use a timeout of at least 60 seconds:

```bash
# Good - 60 second timeout
echo '{"command": ["vision", "/path/to/image.png"]}' | nc -U /run/user/1000/tmp/mmx.sock
```
