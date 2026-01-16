# AI Coder

A fast, lightweight AI-assisted development tool that runs anywhere.

## Installation

### Official Method (Recommended)

```bash
uv tool install git+https://github.com/elblah/v3
```

### Manual Installation

```bash
git clone https://github.com/elblah/v3
cd v3
python main.py
```

## Features

- Built with Python standard library only (no external dependencies)
- Simple, direct code flow
- Environment-based configuration
- Streaming responses with retry logic
- File operation sandbox for security

## Quick Start

```bash
# Set API configuration
export API_BASE_URL="https://api.example.com/v1"
export API_KEY="your-api-key"
export API_MODEL="your-model"

# Run AI Coder
python main.py
```

## Script Integration (Stdin Message Passing)

Pass messages to AI Coder via stdin using pipes. Combined with `YOLO_MODE=1`, the AI will execute the request and exit automatically after completing the task.

```bash
# Simple greeting - AI responds and exits
echo "hello" | YOLO_MODE=1 python main.py

# Execute a command and return the result
echo "exec uname -a" | YOLO_MODE=1 python main.py

# Multiple operations in one prompt
echo "list_directory and read_file /etc/hostname" | YOLO_MODE=1 python main.py
```

### How It Works

1. The message is passed via stdin pipe
2. `YOLO_MODE=1` auto-approves all tool calls (no confirmation needed)
3. AI processes the request and executes tools
4. After the first `stop` reason (finish), the program exits automatically

### Commands in Piped Input

Commands can also be passed via stdin:

```bash
# Show help and exit immediately (no AI call)
echo "/help" | python main.py

# Run council command which posts to AI for expert opinions
echo "/council review this code" | YOLO_MODE=1 python main.py

# Run ralph iterative loop
echo "/ralph implement feature x" | YOLO_MODE=1 python main.py
```

**Command Behavior:**

| Command Type | Examples | AI Call? | Description |
|--------------|----------|----------|-------------|
| **Local Commands** | `/help`, `/stats`, `/new`, `/save` | ❌ No | Execute locally and exit |
| **AI Commands** | `/council`, `/ralph`, regular messages | ✅ Yes | Post to AI for processing |
| **YOLO Mode** | `YOLO_MODE=1 echo "..." \| python main.py` | Auto-approve | All tool calls approved automatically |

### Use Cases

- **CI/CD pipelines**: Run AI tasks as part of build processes
- **Script automation**: Integrate AI into shell scripts
- **Quick queries**: One-off AI commands without interactive mode
- **Pipeline chaining**: Pipe AI output to other commands

```bash
# Get system info and save to file
echo "exec uname -a and exec whoami" | YOLO_MODE=1 python main.py > system_info.txt

# Use in a script
#!/bin/bash
RESULT=$(echo "exec df -h" | YOLO_MODE=1 python main.py)
echo "Disk usage: $RESULT"
```

## Configuration

Configure using environment variables:

- `API_BASE_URL` or `OPENAI_BASE_URL` - API endpoint
- `API_KEY` or `OPENAI_API_KEY` - Authentication key
- `API_MODEL` or `OPENAI_MODEL` - Model name
- `TEMPERATURE` - Response temperature (default: 0.0)
- `MAX_TOKENS` - Maximum tokens (optional)
- `DEBUG=1` - Enable debug mode
- `MAX_RETRIES` - Maximum retry attempts (default: 10)
- `MINI_SANDBOX=0` - Disable sandbox restrictions

## Commands

- `/help` - Show available commands
- `/save` - Save conversation
- `/retry` - Retry the last message
- `/retry limit` - Show current retry limit
- `/retry limit <n>` - Set retry limit (0 = unlimited)
- `/retry help` - Show help for retry command
- `/exit` - Exit the application

## tmux Integration

AI Coder includes a tmux popup menu for quick access to common actions.

### Setup

Add to your `~/.tmux.conf`:

```bash
# Set path to the popup menu script
AICODER_MENU_BIN="$HOME/poc/aicoder/v3/examples/tmux-popup-menu.sh"

# Key bindings
bind-key b run-shell -b "$AICODER_MENU_BIN"
bind -n M-y run-shell -b "$AICODER_MENU_BIN yolo"
bind -n M-d run-shell -b "$AICODER_MENU_BIN detail"
bind -n M-f run-shell -b "$AICODER_MENU_BIN sandbox"
bind -n M-s run-shell -b "$AICODER_MENU_BIN save"
bind -n M-i run-shell -b "$AICODER_MENU_BIN inject"
bind -n M-x run-shell -b "$AICODER_MENU_BIN stop"
bind -n M-k run-shell -b "$AICODER_MENU_BIN kill"
bind -n M-q run-shell -b "$AICODER_MENU_BIN quit"
```

### Key Actions

| Key | Action |
|-----|--------|
| `prefix+b` | Open menu |
| `Alt+y` | Yolo (quick action) |
| `Alt+d` | Detail view |
| `Alt+f` | Sandbox mode |
| `Alt+s` | Save session |
| `Alt+i` | Inject content |
| `Alt+x` | Stop current |
| `Alt+k` | Kill process |
| `Alt+q` | Quit |

## License

See LICENSE file for details.
