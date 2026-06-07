---
name: dtx
description: >
  Dynamic command server via Unix socket. Execute tools, search web, analyze images, browser control, and more.
  Socket at /run/user/1000/tmp/dtx-server.sock.
---

# DTX Command Server

Dynamic Unix socket server that executes commands. Commands evolve over time - always discover first.

## Command Format

```bash
echo "command args..." | nc -U /run/user/1000/tmp/dtx-server.sock
```

**IMPORTANT: Use timeout=300 when calling dtx via run_shell_command.** Some commands (browser start, vision) can be slow, especially on RPi3.

## Discover Available Commands

**Always run this first to know what's available:**

```bash
echo "help" | nc -U /run/user/1000/tmp/dtx-server.sock
```

## Get Help for Specific Command

```bash
echo "help command-name" | nc -U /run/user/1000/tmp/dtx-server.sock
```

## Protocol

- Plain text (not JSON)
- One command per connection
- Output format: `Exit code: N\n\nOutput:\n...\n\nStderr:\n...`
