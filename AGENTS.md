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

## Reference Implementation
Source reference available at: `/mnt/cacho/storage/github/ana`
The Python version should maintain identical functionality and behavior.

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

### Streaming
- Uses Server-Sent Events (SSE) format
- Handles both streaming and non-streaming responses
- Implements retry logic (up to 3 attempts)
- Timeout handling per attempt

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

<REMEMBER_THIS_FOREVER_THIS_IS_A_SPECIAL_RULE>

**NEVER USE SCRIPTS OR MASS REPLACEMENT TOOLS TO CHANGE CODE! NEVER! NEVER! I'm tired of scripts trying to save time end up destroying the codebase and I end up wasting my time reverting the mess**

ALL changes MUST be done safely. The AI should NEVER EVER bypass this rule. If you try I will deny! If you are running in YOLO and I realize later that you did this then I will revert ALL CHANGES IMMEDIATELY... REMEMBER this rule as a BRUTALLY SPECIAL RULE! YOU ARE STRICTLY FORBIDEN FOREVER TO USE ANY MASS REPLACEMENT TOOL (sed, perl, awk... any other) INCLUDING YOUR OWN SCRIPTS IN ANY LANGUAGE WITH THAT PURPOSE!!! You can do scripts that analyze code but
NEVER scripts that change code in mass. ALL CHANGES must be precise there is no place for mistakes!!!

</REMEMBER_THIS_FOREVER_THIS_IS_A_SPECIAL_RULE>

