# AI Coder Python Port

A Python port of the TypeScript AI Coder application - a fast, lightweight AI-assisted development tool that runs anywhere. The goal is to maintain the same architecture and functionality while using only Python standard library.

## Architecture Principles

- **No external dependencies** - uses only Python stdlib
- **Simple and direct** - minimal abstractions, clear code flow
- **Async only when beneficial** - mainly for API streaming
- **Maintain TS structure** - keep same module organization where possible
- **Working over perfect** - prioritize functionality over elegance

## Current Status

### ✅ Phase 1: Core Structure (Complete)
- [x] Configuration system (environment variables)
- [x] Type definitions (dataclasses)
- [x] Logging utilities (ANSI colors, formatting)
- [x] Stats tracking
- [x] Message history
- [x] Input handler
- [x] Tool manager
- [x] Markdown colorizer
- [x] Streaming client (partial)

### ✅ Phase 2: Basic Infrastructure (Complete)
- [x] Internal tools implemented:
  - [x] `read_file` - with sandbox and pagination
  - [x] `write_file` - with directory creation and validation
  - [x] `edit_file` - with exact string replacement
  - [x] `run_shell_command` - with timeout and error handling
  - [x] `grep` - text search with ripgrep/grep fallbacks
  - [x] `list_directory` - directory listing with sandbox

### 🔄 Phase 3: Tool System (In Progress)
- [x] Tool manager with internal and plugin support
- [x] Tool execution workflow
- [x] Tool validation and formatting
- [ ] Advanced tool features (previews, approval system)
- [ ] Plugin system integration

### ⏳ Phase 4: Main Application (Next)
- [ ] Port `AICoder` main class
- [ ] Port command system (`/help`, `/save`, etc.)
- [ ] Port input handling with readline
- [ ] Basic CLI integration

### ⏳ Phase 5: Advanced Features (Later)
- [ ] Message compaction logic
- [ ] Plugin system
- [ ] Remaining features (YOLO mode, etc.)

## Configuration

Uses environment variables:

```bash
# Required
export API_BASE_URL="https://your-api-provider.com/v1"
export API_MODEL="your-model-name"

# Optional
export API_KEY="your-api-key-here"
export TEMPERATURE=0.0
export MAX_TOKENS=4096
export DEBUG=1
export MINI_SANDBOX=1  # Enable filesystem sandbox
```

## Usage

### Basic Usage
```python
from src.core.config import Config
from src.core.stats import Stats
from src.core.tool_manager import ToolManager

# Initialize components
stats = Stats()
tool_manager = ToolManager(stats)

# Execute tools
result = tool_manager.execute_tool_call({
    'id': 'test',
    'function': {
        'name': 'read_file',
        'arguments': '{"path": "example.txt"}'
    }
})
```

### Testing
```bash
# Test the implementation
python test_tools.py

# Run basic startup
python main.py
```

## Technical Notes

### Tools
All tools follow the same pattern:
1. Validation function
2. Format arguments function  
3. Execute function
4. Preview generation (for write/edit operations)

### Sandbox
Simple filesystem sandbox for security:
- Blocks `../` traversal
- Restricts absolute paths to current directory
- Can be disabled with `MINI_SANDBOX=0`

### Streaming
- Uses Server-Sent Events (SSE) format
- Handles both streaming and non-streaming responses
- Implements retry logic (up to 3 attempts)

## Development

### Project Structure
```
src/
├── core/           # Core application logic
├── tools/internal/  # Internal tools
├── types/          # Type definitions
└── utils/          # Utility functions
```

### Testing
Test incrementally:
1. Each module independently
2. Tool system with file operations
3. API streaming with mock responses
4. Full integration with real API

## Next Steps

1. Complete the streaming client implementation
2. Implement the main AICoder class
3. Add command system
4. Integrate with real API
5. Add remaining advanced features

## License

This project maintains the same license as the original TypeScript implementation.