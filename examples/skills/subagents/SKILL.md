---
name: subagents
description: Multi-agent parallel execution system for AI Coder that launches specialized subagents simultaneously to perform complex analyses, documentation generation, code reviews, and research tasks. Use when user requests parallel processing of multiple perspectives, comprehensive analysis from different expert viewpoints, or time-consuming tasks that can be parallelized.
license: Complete terms in LICENSE.txt
---

# Subagents Parallel Execution System

This skill enables AI Coder to launch multiple specialized AI agents in parallel, each with specific tasks, system prompts, and output files. The main agent then synthesizes results from all subagents to provide comprehensive analysis.

## When to Use This Skill

Use this skill when user requests:
- **Multi-perspective analysis**: Security, performance, code quality reviews simultaneously
- **Parallel documentation**: API docs, architecture docs, setup docs at once  
- **Comprehensive research**: Multiple aspects of a topic researched in parallel
- **Time-consuming tasks**: Large codebases or multiple files analyzed simultaneously
- **Specialized expertise**: Different agents with domain-specific system prompts
- **Competitive analysis**: Multiple approaches to same problem compared
- **Hierarchical workflows**: Initial data collection followed by analysis phases

## Core Concepts

### Agent Specialization
Each subagent can have:
- Custom system prompt via `AICODER_SYSTEM_PROMPT` environment variable
- Specific task instructions
- Isolated output file for results
- Individual timeout and retry settings
- **Optional**: Persistent session via `SESSION_FILE` (see Session Persistence below)

### Parallel Execution
- Launch multiple processes in background using `&`
- Capture process IDs for coordination
- Use `wait` for synchronization
- Handle failures and partial results gracefully

### ⚠️ CRITICAL: Environment Variable Placement

**IMPORTANT**: Environment variables (`AICODER_SYSTEM_PROMPT`, `SESSION_FILE`) must be placed **AFTER** the pipe (`|`) to affect the `$AICODER_CMD` process.

**Why this matters:**

Environment variables set BEFORE the pipe apply only to the `echo` command, not to the `$AICODER_CMD` process that receives the piped input.

**❌ INCORRECT pattern:**
```bash
# Variables affect ONLY the echo process, NOT $AICODER_CMD
AICODER_SYSTEM_PROMPT="You are an expert" \
echo "Analyze this" | $AICODER_CMD > output.txt &
```

**✅ CORRECT pattern:**
```bash
# Variables affect $AICODER_CMD (the intended target)
echo "Analyze this" | \
AICODER_SYSTEM_PROMPT="You are an expert" \
$AICODER_CMD > output.txt &
```

**Alternative using export:**
If you export the variable before launching, it works for both sides of the pipe:
```bash
export AICODER_SYSTEM_PROMPT="You are an expert"
echo "Analyze this" | $AICODER_CMD > output.txt &
```

**Best practice:** For subagents, set environment variables immediately before `$AICODER_CMD` to ensure each agent gets its specific settings without polluting the global environment.

### Result Synthesis
- Main agent reads all result files
- Combines, compares, or ranks results
- Provides comprehensive summary
- Handles missing or failed agents appropriately

## Usage Patterns

### Pattern 1: Multi-Expert Code Review
Launch specialized reviewers simultaneously:

```bash
# Security Reviewer
echo "Review the codebase for security issues" | \
AICODER_SYSTEM_PROMPT="You are a SECURITY REVIEWER. Focus only on security vulnerabilities, authentication issues, input validation, and potential attack vectors." \
$AICODER_CMD > security_review.txt &

# Performance Reviewer
echo "Review the codebase for performance issues" | \
AICODER_SYSTEM_PROMPT="You are a PERFORMANCE REVIEWER. Focus only on performance issues, efficiency, resource usage, and scalability concerns." \
$AICODER_CMD > performance_review.txt &

# Code Quality Reviewer
echo "Review the codebase for code quality issues" | \
AICODER_SYSTEM_PROMPT="You are a CODE QUALITY REVIEWER. Focus only on maintainability, design patterns, and best practices." \
$AICODER_CMD > quality_review.txt &

wait  # Wait for all reviews to complete

```

### Pattern 2: Parallel Documentation Generation
Generate different documentation types simultaneously:

```bash
# API Documentation
echo "Extract and document all APIs" | $AICODER_CMD > api_docs.txt &

# Architecture Documentation
echo "Document architecture patterns and design" | $AICODER_CMD > arch_docs.txt &

# Setup Documentation
echo "Document installation and configuration" | $AICODER_CMD > setup_docs.txt &

wait  # Wait for all documentation to complete

```

### Pattern 3: Research and Synthesis
Multiple research angles with final synthesis:

```bash
# Phase 1: Parallel research
echo "Research technical aspects of X" | $AICODER_CMD > technical_research.txt &
echo "Research business aspects of X" | $AICODER_CMD > business_research.txt &
echo "Research user experience aspects of X" | $AICODER_CMD > ux_research.txt &
wait

# Phase 2: Synthesize all research
cat > synthesis_input.txt << EOF
You are a SYNTHESIS EXPERT. Combine insights from three research perspectives:

=== TECHNICAL RESEARCH ===
$(cat technical_research.txt)

=== BUSINESS RESEARCH ===
$(cat business_research.txt)

=== UX RESEARCH ===
$(cat ux_research.txt)

Create comprehensive synthesis covering all aspects.
EOF

cat synthesis_input.txt | $AICODER_CMD > final_synthesis.txt

```

## Configuration Requirements

### Essential Environment Variables
Always set these for reliable subagent execution:

```bash
export YOLO_MODE=1        # Auto-approve all tool actions
export MINI_SANDBOX=0     # Full file access for agents
export MAX_RETRIES=10     # Handle API issues gracefully

```

**Required**: `AICODER_CMD` must be set by AI Coder wrapper script. Never set this in subagent scripts - it is provided externally.

Check if `AICODER_CMD` is set before launching subagents:
```bash
if [ -z "$AICODER_CMD" ]; then
    echo "Error: AICODER_CMD environment variable is not set."
    echo "This should be provided by AI Coder wrapper script."
    exit 1
fi

```

Use `$AICODER_CMD` when launching subagents:
```bash
$AICODER_CMD ...

```
### Optional Performance Tuning
```bash
export CONTEXT_SIZE=32000          # Smaller context for faster processing
export STREAMING_TIMEOUT=120       # Longer timeout for complex tasks
export STREAMING_READ_TIMEOUT=30  # Per-read timeout

```

## Important Usage Guidelines

### When Launching Subagents
ALWAYS inform the user about:
- Number of subagents being launched
- Name and purpose of each agent
- Estimated completion time
- Where results will be stored

**Example notification:**
> "Launching 4 subagents in parallel:
> - Security Agent: Analyzing vulnerabilities and attack vectors
> - Performance Agent: Identifying bottlenecks and optimization opportunities  
> - Documentation Agent: Generating API and architecture docs
> - Testing Agent: Reviewing test coverage and strategies
> 
> This will take approximately 2-3 minutes. Results will be saved to /tmp/subagent_analysis/"

### Timeout Management
**IMPORTANT**: Use generous timeouts when running subagent scripts via `run_shell_command`:

```bash
# Recommended timeout settings
run_shell_command "./launch_subagents.sh" timeout=300  # 5 minutes for basic parallel tasks
run_shell_command "./subagent_orchestrator.sh" timeout=600  # 10 minutes for complex workflows
run_shell_command "./comprehensive_analysis.sh" timeout=900  # 15 minutes for large codebases

```

**Timeout guidelines:**
- **2-4 agents**: 180-300 seconds (3-5 minutes)
- **5-10 agents**: 300-600 seconds (5-10 minutes)  
- **Complex workflows**: 600-900 seconds (10-15 minutes)
- **Large codebases**: 900-1800 seconds (15-30 minutes)

### Error Handling
Always handle scenarios where:
- Some agents fail while others succeed
- API rate limits cause intermittent failures
- Memory constraints limit parallel execution
- Output files are corrupted or incomplete

**Recovery strategy:**
1. Check which output files were created and contain valid results
2. Re-launch only failed agents if needed
3. Provide partial results with clear indication of what's missing
4. Offer to retry full execution if user desires

## Available Scripts

> **⚠️ IMPORTANT**: The scripts listed below are **examples and suggestions only**. They demonstrate the subagent patterns and workflows but are not mandatory. Feel free to modify them or create your own custom scripts based on your specific needs. The key is understanding the patterns (parallel execution, environment variable placement, session persistence) rather than copying these scripts exactly.

### Core Scripts
- `scripts/launch_subagents.sh` - Basic 4-agent parallel launcher
- `scripts/subagent_orchestrator.sh` - Advanced 5-agent + synthesis workflow  
- `scripts/subagent_runner.sh` - Dynamic utility for arbitrary parallel tasks

### Reference Material
- `references/README.md` - Complete technical documentation
- `references/IMPLEMENTATION_GUIDE.md` - Technical deep dive and internals
- `references/RECIPES.md` - 12+ ready-to-use patterns and workflows
- `references/TROUBLESHOOTING.md` - Debugging, recovery, and prevention

## Common Workflows

### Quick Code Review
```bash
# 3-perspective review (security, performance, quality)
echo "Perform comprehensive code review with security, performance, and quality perspectives" | 
cat > /tmp/review_request.txt << EOF
Launch parallel code review:
- Security agent: Check for vulnerabilities and security issues
- Performance agent: Identify bottlenecks and optimization opportunities
- Code quality agent: Review maintainability and best practices
EOF

./scripts/subagent_runner.sh "Security-focused code review" "Performance-focused code review" "Code quality and maintainability review"

```

### Documentation Generation
```bash
# Complete documentation package
echo "Generate comprehensive documentation package" | 
./scripts/subagent_orchestrator.sh

```

### Security Audit
```bash
# Specialized security analysis
export AICODER_SYSTEM_PROMPT="You are a SECURITY AUDITOR. Focus exclusively on security vulnerabilities, authentication flaws, input validation issues, and potential attack vectors. Provide specific, actionable findings."

echo "Conduct comprehensive security audit of this codebase" | 
./scripts/subagent_runner.sh "Authentication and authorization review" "Input validation and injection vulnerabilities" "File system and permission security" "API security analysis"

```

## Best Practices

### Resource Management
- Limit concurrent agents to available memory (200MB per agent estimate)
- Stagger agent launches by 1-2 seconds to avoid API rate limits
- Use appropriate timeouts based on task complexity

### Quality Assurance
- Validate each output file before synthesis
- Check for "AI:" response markers indicating successful completion
- Handle empty or corrupted files gracefully

### User Experience
- Always provide clear progress indicators
- Show agent names and purposes
- Give realistic time estimates
- Explain what each agent is doing

## Advanced Features

### Hierarchical Agent Execution
Multi-phase workflows where later agents depend on earlier results:

```bash
# Phase 1: Data collection
echo "Extract all API endpoints" | $AICODER_CMD > endpoints.txt &
echo "List all database queries" | $AICODER_CMD > queries.txt &
wait

# Phase 2: Analysis of collected data
echo "Analyze these endpoints for security: $(cat endpoints.txt)" | $AICODER_CMD > endpoint_security.txt &
echo "Analyze these queries for performance: $(cat queries.txt)" | $AICODER_CMD > query_performance.txt &
wait

# Phase 3: Final synthesis
echo "Create security report from: endpoint_security.txt + query_performance.txt" | $AICODER_CMD > final_security_report.txt

```

### Competitive Analysis
Multiple approaches to same problem for comparison:

```bash
# Different architectures for same task
echo "Design authentication system" | \
AICODER_SYSTEM_PROMPT="You are an ENTERPRISE ARCHITECT. Focus on scalability, maintainability, and enterprise patterns." \
$AICODER_CMD > enterprise_design.txt &

echo "Design authentication system" | \
AICODER_SYSTEM_PROMPT="You are a STARTUP ARCHITECT. Focus on speed, simplicity, and rapid development." \
$AICODER_CMD > startup_design.txt &

echo "Design authentication system" | \
AICODER_SYSTEM_PROMPT="You are a SECURITY ARCHITECT. Focus on zero-trust, encryption, and defense in depth." \
$AICODER_CMD > security_design.txt &

wait

# Compare and recommend
echo "Compare these three authentication designs and recommend best approach: enterprise_design.txt + startup_design.txt + security_design.txt" | $AICODER_CMD > design_comparison.txt

```

## Session Persistence (Advanced Feature)

### Overview

The `session-autosaver` plugin enables subagents to maintain persistent conversation history via the `SESSION_FILE` environment variable. This is an **optional advanced feature** - use it only when it provides clear value.

### Session Autosaver Plugin

**Location**: `plugins/session-autosaver.py`

**What it does**:
- Automatically loads and saves session to `SESSION_FILE` in JSONL format
- Auto-loads existing session on startup
- Auto-appends messages (user, assistant, tool) during execution
- Supports both `.json` and `.jsonl` formats (detected from file extension)

**Activation**: The plugin activates automatically when `SESSION_FILE` is set. No other configuration needed.

**⚠️ AI Requirements**: When using SESSION_FILE, the AI must inform the user:
> "⚠️ Using session persistence feature. This requires the `session-autosaver` plugin (auto-activates when SESSION_FILE is set)."

### Minimal Session Persistence Example

This is the simplest possible test of session persistence - setting a value in one call and recalling it in another:

```bash
#!/bin/bash
# Minimal session persistence test

export YOLO_MODE=1
export MINI_SANDBOX=0
export MAX_RETRIES=10
export SESSION_FILE="/tmp/simple_test.jsonl"

if [ -z "$AICODER_CMD" ]; then
    echo "Error: AICODER_CMD not set"
    exit 1
fi

# Phase 1: Store information
echo "My name is Alex. Remember this." | \
SESSION_FILE="$SESSION_FILE" \
$AICODER_CMD

# Phase 2: Recall information
echo "What is my name?" | \
SESSION_FILE="$SESSION_FILE" \
$AICODER_CMD

# Verify session file exists
cat "$SESSION_FILE"
```

**Expected behavior:**
- Phase 1: AI responds and creates `simple_test.jsonl` with the conversation
- Phase 2: AI loads the session and correctly recalls "Alex"
- Both phases use the same session file, so memory persists

**Note the critical placement:** `SESSION_FILE` is set AFTER the pipe, before `$AICODER_CMD`.

### When to Use Session Persistence

**✅ Use when**:
- Multi-phase workflows where later phases build on earlier work
- Agent will be called multiple times with related tasks
- Need to resume analysis later or debug agent behavior
- Progressive deep-dive analysis (initial scan → detailed analysis → final report)

**❌ Don't use when**:
- Single-shot, one-time analysis
- Independent parallel tasks that don't share context
- Simple workflows where session overhead isn't justified
- Performance-critical scenarios where extra I/O is problematic

### Usage Pattern

```bash
# Phase 1: Initial analysis - session will be saved
echo "Phase 1: Conduct broad security scan" | \
AICODER_SYSTEM_PROMPT="You are a SECURITY AUDITOR. Track findings systematically." \
SESSION_FILE="/tmp/security_session.jsonl" \
$AICODER_CMD > phase1.txt &
PID1=$!
wait $PID1

# Phase 2: Deep dive - session loaded, can reference Phase 1 findings
echo "Phase 2: Deep dive analysis based on Phase 1 findings" | \
AICODER_SYSTEM_PROMPT="You are a SECURITY AUDITOR. Track findings systematically." \
SESSION_FILE="/tmp/security_session.jsonl" \
$AICODER_CMD > phase2.txt &
PID2=$!
wait $PID2

```

### Session File Format

**JSONL format** (recommended - one JSON per line):
```jsonl
{"role": "system", "content": "You are a SECURITY AUDITOR..."}
{"role": "user", "content": "Phase 1: Conduct broad security scan"}
{"role": "assistant", "content": "Found 3 vulnerabilities..."}
{"role": "user", "content": "Phase 2: Deep dive analysis..."}

```

**JSON format** (backward compatible - array):
```json
[
  {"role": "system", "content": "You are a SECURITY AUDITOR..."},
  {"role": "user", "content": "Phase 1: Conduct broad security scan"}
]

```

Format is automatically detected from file extension (`.jsonl` vs `.json`).

### AI Decision Flow


```
Is the agent being called multiple times with related tasks?
  ├─ YES → Will later calls need context from earlier calls?
  │         ├─ YES → Use SESSION_FILE
  │         └─ NO  → Don't use SESSION_FILE
  └─ NO  → Don't use SESSION_FILE

```

### Example: Multi-Phase Security Audit

```bash
#!/bin/bash
export YOLO_MODE=1
export MINI_SANDBOX=0
export MAX_RETRIES=10

AUDIT_DIR="/tmp/security_audit_$(date +%s)"
mkdir -p "$AUDIT_DIR"

# Phase 1: Initial scan with persistent session
echo "Conduct initial security scan focusing on authentication and authorization" | \
AICODER_SYSTEM_PROMPT="You are a SECURITY AUDITOR. Track all findings systematically." \
SESSION_FILE="$AUDIT_DIR/audit_session.jsonl" \
$AICODER_CMD > "$AUDIT_DIR/phase1_initial.txt" &
PID1=$!
wait $PID1

# Phase 2: Deep dive using previous context
echo "Based on initial findings, conduct deep dive on input validation and SQL injection" | \
AICODER_SYSTEM_PROMPT="You are a SECURITY AUDITOR. Track all findings systematically." \
SESSION_FILE="$AUDIT_DIR/audit_session.jsonl" \
$AICODER_CMD > "$AUDIT_DIR/phase2_deepdive.txt" &
PID2=$!
wait $PID2

# Phase 3: Final synthesis
echo "Create comprehensive security report with severity levels and remediation steps" | \
AICODER_SYSTEM_PROMPT="You are a SECURITY AUDITOR. Track all findings systematically." \
SESSION_FILE="$AUDIT_DIR/audit_session.jsonl" \
$AICODER_CMD > "$AUDIT_DIR/phase3_final_report.txt" &
PID3=$!
wait $PID3

echo "✅ Multi-phase audit complete!"
echo "📁 Results: $AUDIT_DIR"
echo "💾 Session history: $AUDIT_DIR/audit_session.jsonl"

```

## Keywords

subagents, parallel agents, multi-agent, concurrent processing, parallel execution, simultaneous analysis, multi-perspective review, code review, security audit, performance analysis, documentation generation, research synthesis, competitive analysis, hierarchical workflow, session persistence, SESSION_FILE, session autosaver, multi-phase workflow