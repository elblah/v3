# Subagent System for AI Coder

## Overview

The subagent system enables AI Coder to launch multiple parallel AI agents simultaneously, each with specialized tasks or perspectives. This is achieved through a simple yet powerful combination of:

1. **Environment-based configuration** - Each subprocess can have different settings
2. **Stdin piping** - Tasks are piped to `python main.py` in non-interactive mode
3. **Process backgrounding** - Multiple agents run in parallel using `&`
4. **File-based result collection** - Each agent outputs to a separate file
5. **Process orchestration** - Main script coordinates launch, wait, and synthesis

## Core Concepts

### 1. Agent Specialization via Environment Variables

```bash
# Custom system prompt for specialized agent
AICODER_SYSTEM_PROMPT="You are a SECURITY ANALYZER. Focus only on security aspects..."

# Override any configuration per agent
YOLO_MODE=1                    # Auto-approve all tool actions
MINI_SANDBOX=0                 # Disable file sandbox
MAX_RETRIES=10                 # Increase retry attempts
TEMPERATURE=0.2                # More deterministic output
```

### 2. Parallel Process Management

```bash
# Launch multiple agents in background
echo "task 1" | python main.py > /tmp/result1.txt &
PID1=$!

echo "task 2" | python main.py > /tmp/result2.txt &
PID2=$!

# Wait for all to complete
wait $PID1 $PID2
```

### 3. Non-Interactive Execution

AI Coder automatically detects when running in non-interactive mode:
- `sys.stdin.isatty()` returns `False` when input is piped
- Single line of input is processed and output returned
- No interactive prompts or context bars shown

### 4. Result Synthesis

After parallel execution, a main agent can read all result files:
```bash
cat > combined_input.txt << EOF
Read these analyses and synthesize:
=== SECURITY ===
$(cat /tmp/security_analysis.txt)

=== PERFORMANCE ===
$(cat /tmp/performance_analysis.txt)
EOF
cat combined_input.txt | python main.py
```

## Technical Implementation Details

### Timeout Management

**Problem**: Subagents can take varying amounts of time, and some may get stuck.

**Solutions**:

1. **Per-agent timeouts** in scripts:
```bash
timeout 60s python main.py > result.txt &
```

2. **Global timeout** in orchestrator:
```bash
# Set maximum wait time for all agents
timeout 300s bash -c "wait $PID1 $PID2 $PID3"
```

3. **Retry configuration**:
```bash
export MAX_RETRIES=10  # More retries for reliability
```

### Resource Management

**Memory Usage**: Each subprocess loads the full AI Coder context. Consider:
- Limiting parallel agents based on available memory
- Using smaller context sizes for specialized agents

**API Rate Limits**: Multiple parallel agents can hit API limits:
- Implement staggered launches if needed
- Use MAX_RETRIES to handle temporary rate limits

### Error Handling

**Failed Agents**: Scripts should handle when some agents fail:
```bash
# Wait for agents individually with error handling
wait $PID1 || echo "Agent 1 failed"
wait $PID2 || echo "Agent 2 failed"
```

**Partial Results**: Synthesize only successful results:
```bash
if [ -f "/tmp/result1.txt" ]; then
    echo "=== Agent 1 Results ===" >> combined.txt
    cat /tmp/result1.txt >> combined.txt
fi
```

## Best Practices

### 1. Agent Design

- **Keep tasks focused**: Each agent should have a specific, well-defined task
- **Use appropriate prompts**: More specific prompts = better results
- **Consider token limits**: Complex prompts may need smaller context sizes

### 2. Orchestration

- **Check dependencies**: Ensure prerequisites before launching agents
- **Monitor resource usage**: Don't overwhelm the system
- **Plan for failures**: Design synthesis to handle partial results

### 3. Performance Optimization

- **Batch similar tasks**: Group agents with similar workloads
- **Use caching**: Store results that might be reused
- **Parallelize strategically**: Not everything needs to be parallel

## Common Patterns

### Pattern 1: Multi-Perspective Analysis

```bash
# Launch expert agents with different perspectives
AICODER_SYSTEM_PROMPT="You are a SECURITY EXPERT..." \
echo "Analyze security..." | python main.py > security.txt &

AICODER_SYSTEM_PROMPT="You are a PERFORMANCE EXPERT..." \
echo "Analyze performance..." | python main.py > performance.txt &

AICODER_SYSTEM_PROMPT="You are a USABILITY EXPERT..." \
echo "Analyze usability..." | python main.py > usability.txt &

wait  # Wait for all
# Synthesize results...
```

### Pattern 2: Parallel File Processing

```bash
# Process multiple files simultaneously
for file in *.md; do
    echo "Summarize $file" | python main.py > "summary_$(basename $file)" &
done
wait  # All summaries complete
```

### Pattern 3: Hierarchical Analysis

```bash
# Phase 1: Collect raw data
echo "Extract all API endpoints" | python main.py > endpoints.txt &
echo "List all database queries" | python main.py > queries.txt &
wait

# Phase 2: Analysis based on collected data
echo "Analyze these endpoints for security issues: $(cat endpoints.txt)" | python main.py > security_analysis.txt &
```

## Limitations and Considerations

### Resource Constraints
- Each agent loads full context into memory
- Parallel API calls may hit rate limits
- File I/O can become bottleneck with many agents

### Coordination Complexity
- Managing many background processes becomes complex
- Error handling becomes more difficult at scale
- Debugging parallel execution is challenging

### State Management
- Agents share no state between them
- Result synthesis depends on file ordering
- No mechanism for agent-to-agent communication

## Future Enhancements

### Possible Improvements

1. **Agent Communication**: Allow agents to pass messages or results to each other
2. **Dynamic Task Allocation**: Agents can spawn other agents as needed
3. **Resource Pooling**: Shared context or caching between agents
4. **Advanced Orchestration**: More sophisticated workflow management
5. **Agent Specialization Registry**: Pre-defined agent types and configurations

### Integration with AI Coder Core

This subagent system could be integrated as:
- A core skill for launching parallel agents
- Built-in orchestration commands
- Plugin system for agent types and workflows
- Socket-based agent coordination for more complex scenarios

## Example Scripts

### Basic Parallel Launcher
See `launch_subagents.sh` - simple 4-agent parallel execution with mixed custom/default prompts.

### Advanced Orchestrator  
See `subagent_orchestrator.sh` - 5 specialized agents + synthesis agent with comprehensive workflow.

### Utility Runner
See `subagent_runner.sh` - dynamic agent creation from command line arguments.

## Conclusion

The subagent system demonstrates how AI Coder can scale from single-agent operation to sophisticated multi-agent orchestration using only:
- Environment variables for configuration
- Process management for parallelism  
- File I/O for communication
- Shell scripting for orchestration

This approach maintains AI Coder's minimalist philosophy while enabling powerful parallel processing capabilities.