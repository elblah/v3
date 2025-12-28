# AI Coder - Project Documentation

## Project Overview
AI Coder is a fast, lightweight AI-assisted development tool that runs anywhere. Built using only Python standard library with no external dependencies.

## Architecture Principles
- **No external dependencies** - uses only Python stdlib
- **Simple and direct** - minimal abstractions, clear code flow
- **Working over perfect** - prioritize functionality over elegance
- **Systematic approach** - incremental progress with clear verification

## Key Constraints
- Use `urllib` for HTTP requests (no requests library)
- Keep the same tool system and API surface
- Maintain environment-based configuration
- Preserve the command system (`/help`, `/save`, etc.)

## Development Approach

### Systematic Porting Method
Following the Anthropic long-running agent approach:
1. **Initializer phase**: Complete analysis and feature mapping
2. **Incremental implementation**: One component at a time
3. **Verification each step**: Test against reference behavior
4. **Clean commits**: Each component completion is committed

### Progress Tracking
Progress is tracked in `port-progress.json` with:
- Component status (pending/in-progress/complete)
- Sub-feature breakdown
- Test verification status
- Reference file mappings

## Technical Notes

### Configuration
Uses environment variables:
- `API_BASE_URL` or `OPENAI_BASE_URL` - API endpoint
- `API_KEY` or `OPENAI_API_KEY` - Authentication (optional)
- `API_MODEL` or `OPENAI_MODEL` - Model name
- `TEMPERATURE` - Temperature (default: 0.0)
- `MAX_TOKENS` - Max tokens (optional)
- `DEBUG=1` - Debug mode

### Tools
All tools follow same pattern:
1. Validation function
2. Format arguments function
3. Execute function
4. Return structured output

IMPORTANT: use system tools when the reference uses them like diff, ripgrep, find...

### Streaming & Retry
- Uses Server-Sent Events (SSE) format
- Handles both streaming and non-streaming responses
- Implements retry logic with visible error messages
- Configurable via `MAX_RETRIES` environment variable (default: 3)
- Runtime control: `/retry limit <n>` command (0 = unlimited)
- Shows retry progress: `Attempt 1/3 failed: <error>. Retrying in 2s...`
- Exponential backoff: 2s, 4s, 8s, 16s, 32s, 64s (capped)
- Timeout handling per attempt

### Sandbox
Simple sandbox for file operations:
- Blocks `../` traversal
- Restricts absolute paths to current directory
- Can be disabled with `MINI_SANDBOX=0`

### Sandbox
Simple sandbox for file operations:
- Blocks `../` traversal
- Restricts absolute paths to current directory
- Can be disabled with `MINI_SANDBOX=0`

## Comments
1. Keep comments professional. Comments must detail what the code does and not history.
2. Focus on functionality, not implementation details
3. Reference the TS implementation for exact behavior matching


## SUPER IMPORTANT

**ABSOLUTELY FORBIDDEN: Mass-replacement tools or scripts**

The following operations are strictly forbidden:
- `sed`, `awk`, `perl` or any mass-replacement command
- Python scripts or other scripts that modify multiple files
- Any tool that performs batch/automated code changes

**Rationale:** Mass changes lack context and frequently break:
- Python indentation (syntax errors)
- Code blocks and structure
- Edge cases only visible with full context

**Requirement:** ALL code changes must be:
- Precise and intentional
- Made with full context of the target file
- One change at a time using proper edit tools

**Exception:** Analysis scripts that only read/inspect code (not modify) are permitted.

