# AI Coder

A fast, lightweight AI-assisted development tool that runs anywhere.

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

## Configuration

Configure using environment variables:

- `API_BASE_URL` or `OPENAI_BASE_URL` - API endpoint
- `API_KEY` or `OPENAI_API_KEY` - Authentication key
- `API_MODEL` or `OPENAI_MODEL` - Model name
- `TEMPERATURE` - Response temperature (default: 0.0)
- `MAX_TOKENS` - Maximum tokens (optional)
- `DEBUG=1` - Enable debug mode
- `MAX_RETRIES` - Maximum retry attempts (default: 3)
- `MINI_SANDBOX=0` - Disable sandbox restrictions

## Commands

- `/help` - Show available commands
- `/save` - Save conversation
- `/retry limit <n>` - Set retry limit (0 = unlimited)
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
