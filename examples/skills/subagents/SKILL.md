---
name: subagents
description: Launch multiple AI Coder agents in parallel for multi-perspective analysis, code review, research, and documentation. Use when user requests parallel processing or multiple expert viewpoints.
---

# Subagents: Parallel AI Execution

Launch multiple AI Coder agents simultaneously, each with specialized focus. Main agent synthesizes results when all complete.

## Quick Example

```bash
export YOLO_MODE=1
export MINI_SANDBOX=0

# Launch 3 agents in parallel (env vars AFTER pipe!)
echo "Review code for security issues" | \
AICODER_SYSTEM_PROMPT="You are a SECURITY AUDITER. Be brief, list specific findings." \
$AICODER_CMD > /tmp/security.txt &

echo "Review code for performance issues" | \
AICODER_SYSTEM_PROMPT="You are a PERFORMANCE ANALYZER. Be brief, list specific findings." \
$AICODER_CMD > /tmp/performance.txt &

echo "Review code for maintainability" | \
AICODER_SYSTEM_PROMPT="You are a CODE QUALITY REVIEWER. Be brief, list specific findings." \
$AICODER_CMD > /tmp/quality.txt &

wait # Sync all agents

# Synthesize results
cat /tmp/security.txt /tmp/performance.txt /tmp/quality.txt
```

## Critical: Env Var Placement

```
✅ echo "task" | VAR=value $AICODER_CMD   # var affects aicoder
❌ VAR=value echo "task" | $AICODER_CMD   # var affects echo only!
```

Alternative: export before launching (affects both sides of pipe):
```bash
export AICODER_SYSTEM_PROMPT="You are an expert"
echo "Analyze this" | $AICODER_CMD > output.txt &
```

## Orchestration Scripts

Create scripts in `/tmp`, never in project root:

```bash
SCRIPT_DIR="/tmp/subagent_$(date +%s%N)"
mkdir -p "$SCRIPT_DIR"

cat > "$SCRIPT_DIR/run.sh" << 'EOF'
#!/bin/bash
set -e
export YOLO_MODE=1
export MINI_SANDBOX=0

if [ -z "$AICODER_CMD" ]; then
  echo "Error: AICODER_CMD not set (should be provided by aicoder wrapper)"
  exit 1
fi

echo "Analyze X" | $AICODER_CMD > /tmp/x.txt &
echo "Analyze Y" | $AICODER_CMD > /tmp/y.txt &
wait
EOF

chmod +x "$SCRIPT_DIR/run.sh"
"$SCRIPT_DIR/run.sh"
rm -rf "$SCRIPT_DIR" # cleanup
```

## Available Scripts

| Script | Purpose |
|--------|---------|
| `scripts/launch_basic.sh` | 4-agent basic analysis |
| `scripts/code_review.sh` | Security/performance/quality review |
| `scripts/documentation_generator.sh` | API, arch, setup docs |
| `scripts/parallel_runner.sh` | Dynamic N-agent launcher |
| `scripts/comprehensive_analysis.sh` | Complex multi-phase workflow |

## Session Persistence (Optional)

For multi-phase workflows where later phases need earlier context:

```bash
# Phase 1: Save session
echo "Task 1" | SESSION_FILE=/tmp/session.jsonl $AICODER_CMD > /tmp/phase1.txt &

# Phase 2: Load session, continue
echo "Task 2" | SESSION_FILE=/tmp/session.jsonl $AICODER_CMD > /tmp/phase2.txt &
wait
```

Requires `session-autosaver` plugin (auto-activates when SESSION_FILE is set).

## Hierarchical Workflows

```
Phase 1: Parallel data collection
→ echo "Extract X" | $AICODER_CMD > /tmp/x.txt &
→ echo "Extract Y" | $AICODER_CMD > /tmp/y.txt &
→ wait

Phase 2: Parallel analysis on collected data
→ echo "Analyze: $(cat /tmp/x.txt)" | $AICODER_CMD > /tmp/analyze_x.txt &
→ echo "Analyze: $(cat /tmp/y.txt)" | $AICODER_CMD > /tmp/analyze_y.txt &
→ wait

Phase 3: Synthesis
→ echo "Create report from: $(cat /tmp/analyze_x.txt /tmp/analyze_y.txt)" | $AICODER_CMD > /tmp/report.txt
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `AICODER_CMD` | Path to aicoder binary (**provided by wrapper, do NOT set**) | - |
| `YOLO_MODE=1` | Auto-approve all actions | - |
| `MINI_SANDBOX=0` | Full file access | 1 |
| `MAX_RETRIES=10` | API retry attempts | 3 |
| `AICODER_SYSTEM_PROMPT` | Custom system prompt per agent | - |
| `SESSION_FILE` | Persist session (requires plugin) | - |
| `TOOLS_ALLOW` | Comma-separated tool whitelist | all |
| `CONTEXT_SIZE` | Smaller context for faster processing | default |
| `TOTAL_TIMEOUT` | Total timeout in seconds | default |

## TOOLS_ALLOW

Restrict subagent tool access for safe analysis:

```bash
# Read-only analysis (safe, no modifications)
echo "Analyze patterns" | TOOLS_ALLOW="read_file,grep,list_directory" $AICODER_CMD > /tmp/analysis.txt &

# Review only (no write access)
echo "Review code quality" | TOOLS_ALLOW="read_file,grep" $AICODER_CMD > /tmp/review.txt &
```

Available tools: `read_file`, `write_file`, `edit_file`, `run_shell_command`, `grep`, `list_directory`

## Timeout Guidelines

| Agents | Complexity | Timeout |
|--------|------------|---------|
| 2-4 | Simple | 180-300s |
| 5-10 | Medium | 300-600s |
| Complex | Multi-phase | 600-900s |

## Error Handling

- Check output files exist before reading
- Re-launch failed agents if needed
- Provide partial results if some agents fail
- Use `tail` to verify output quality

## Keywords

subagents, parallel, multi-agent, code review, security audit, research, documentation, concurrent
