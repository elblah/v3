# Council Plugin

Get expert opinions from AI council members on your code and implementations.

## Quick Start

```bash
# Install example council members
cd examples/council
./install.sh
```

## Usage

### Normal Council Mode

Ask questions and get expert opinions:

```
/council Review my code for bugs and best practices
/council --direct Get opinions without moderation
/council --members security,ux Check security and UX only
```

**How it works:**
1. Loads council members from `.aicoder/council/` directory
2. Each member (e.g., code reviewer, security expert) gives their opinion
3. If `moderator.txt` exists, it synthesizes opinions into a summary
4. Otherwise, all opinions go directly to the AI

**Accept feedback:**
```
/council current    # Show current council plan
/council accept     # Inject plan into conversation
/council clear      # Clear session
```

### Auto-Council Mode

Iterative implementation with validation until all experts approve:

```
/council --auto spec.md                # Auto-implement from spec file
/council --auto "Build a REST API"     # Auto-implement from inline spec
/council --auto --reset-context spec.md # Fresh context each iteration
/council --auto --no-reset spec.md     # Preserve context across iterations
```

**How it works:**
1. Loads specification and injects into conversation
2. AI implements the specification
3. AI finishes and hands over to user
4. Council (auto-members only) reviews implementation
5. Each member votes: `IMPLEMENTATION_FINISHED` or `IMPLEMENTATION_NOT_FINISHED`
6. If ALL members vote FINISHED → Complete
7. Otherwise → Feedback injected, AI continues
8. Repeat until all approve or max iterations reached

## Council Members

### File Naming

Members are plain text files in `.aicoder/council/`:

- `01_code_reviewer.txt` - Normal mode member
- `01_code_reviewer_auto.txt` - Auto-council member (ends with `_auto`)
- `moderator.txt` - Synthesizes opinions in normal mode
- `_disabled_member.txt` - Disabled (starts with underscore)

### Member Format

```
You are a Code Reviewer.

Your role is to review code quality and identify issues.

Check for:
- Code clarity and readability
- Proper error handling
- Efficient algorithms

Provide concise feedback. Limit to 300 words.
```

**NOTE**: For auto-members (`*_auto.txt`), the system automatically appends:
- Role clarification (you are a council member, not the implementing AI)
- Voting instructions (MUST use `IMPLEMENTATION_FINISHED` or `IMPLEMENTATION_NOT_FINISHED`)
- Tool usage restrictions (you cannot execute tools)

**Voting System is NOT Flexible**: Only two votes are valid:

- `IMPLEMENTATION_FINISHED` - Implementation is complete (even if it exceeds requirements)
- `IMPLEMENTATION_NOT_FINISHED` - Implementation needs changes

**Invalid votes (treated as NO_VOTE)**:
- `IMPLEMENTATION_EXCEEDS_SPECIFICATION` ❌
- `APPROVED` ❌
- `IMPLEMENTATION_COMPLETE` ❌
- Any other creative phrase ❌

Member files should focus ONLY on their specific expertise area, not repeat generic voting rules.

The system automatically appends voting instructions to auto-members.

## Configuration

Environment variables:

```bash
COUNCIL_MAX_ITERATIONS=10    # Max auto-council loops (default: 10)
```

## Available Commands

```
/council <message>                              Get opinions from all members
/council --direct <message>                     Direct opinions (no moderator)
/council --members member1,member2 <message>    Specific members
/council --auto                                 Open editor to create spec
/council --auto <spec.md>                        Auto-iterate with spec file
/council --auto "text message"                   Auto-iterate with text spec
/council --auto --reset-context <spec.md>        Fresh context each turn
/council --auto --no-reset <spec.md>             Preserve context
/council current                                 Show current council plan
/council accept                                  Accept and inject plan
/council clear                                   Clear current session
/council list                                    Show available members
/council edit <number|name>                      Edit member file
/council enable <number|name>                    Enable member
/council disable <number|name>                   Disable member
```

## Architecture

**Plugin file:** `plugins/05_council.py` (self-contained, no dependencies)

**Key components:**
- `CouncilService` - Manages council state, member loading, opinion gathering
- `CouncilCommand` - Parses and executes `/council` commands
- Hook integration - `after_ai_processing` hook triggers auto-council

**Auto-council flow:**

```
User: /council --auto spec.md
  → Load spec
  → Inject spec into conversation
  → set_next_prompt("Implement this specification")
  → AI implements
  → AI finishes (no tool calls)
  → Hook: after_ai_processing (has_tool_calls=FALSE)
  → Council reviews (auto-members only)
  → If all FINISHED → stop
  → Else → inject feedback, set_next_prompt("Continue...")
  → AI continues
  → Repeat...
```

## Example Members Included

- `01_code_reviewer_auto.txt` - Code quality review
- `02_security_expert_auto.txt` - Security vulnerability checks
- `03_simplicity_advocate_auto.txt` - Simplicity/complexity checks
- `04_spec_validator_auto.txt` - Spec compliance validation
- `05_coach_auto.txt` - Project coach ensures task completion and prevents deviations
- `moderator_auto.txt` - Synthesizes opinions (normal mode)

## Troubleshooting

**Council members not responding:**
- Check API key is set
- Check member files exist in `.aicoder/council/`
- Enable debug mode: `DEBUG=1`

**Auto-council loops forever:**
- Check member voting - they must end with `IMPLEMENTATION_FINISHED` or `IMPLEMENTATION_NOT_FINISHED`
- Increase max iterations: `COUNCIL_MAX_ITERATIONS=20`

**No moderator synthesis:**
- Ensure `moderator.txt` exists in `.aicoder/council/`
- Check it's not disabled (no `_` prefix)
