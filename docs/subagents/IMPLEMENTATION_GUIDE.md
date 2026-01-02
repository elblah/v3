# Subagent Implementation Guide

## Technical Deep Dive

### How It Works Under the Hood

The subagent system leverages AI Coder's architecture to enable parallel execution:

```
Bash Script → Environment Variables → Stdin → python main.py → Tool Execution → File Output
     ↓                    ↓              ↓           ↓              ↓            ↓
Process            AICODER_...      Non-interactive  Agent runs    Tools use   Results
Management        Config           Mode             with custom    built-in    captured
                                                    prompts        tools
```

### Key AI Coder Features Used

1. **Non-Interactive Mode Detection**
   ```python
   # In input_handler.py
   if not sys.stdin.isatty():
       return sys.stdin.readline() or ""
   ```

2. **Environment-Based Configuration**
   ```python
   # In config.py
   @staticmethod
   def system_prompt() -> str:
       return os.environ.get("AICODER_SYSTEM_PROMPT") or ""
   ```

3. **Stdin Processing Pipeline**
   ```python
   # In aicoder.py -> run_non_interactive()
   user_input = read_stdin_as_string()
   lines = user_input.strip().split("\n")
   for line in lines:
       # Process each line...
   ```

### Process Flow Analysis

#### Step 1: Agent Launch
```bash
AICODER_SYSTEM_PROMPT="..." echo "task" | python main.py > output.txt &
```

What happens:
1. **Environment Setup**: `AICODER_SYSTEM_PROMPT` exported for subprocess
2. **Process Fork**: New Python process starts
3. **Stdin Redirection**: `echo "task"` becomes stdin for python process
4. **Output Redirection**: All stdout/stderr goes to `output.txt`
5. **Backgrounding**: `&` puts process in background

#### Step 2: Agent Execution
Inside each python process:

1. **Import Phase**: All AI Coder modules loaded
2. **Config Phase**: Environment variables read and applied
3. **Init Phase**: AICoder instance created with custom config
4. **Non-Interactive Detection**: `sys.stdin.isatty()` returns False
5. **Stdin Processing**: Single line read from pipe
6. **Tool Execution**: AI agent uses tools to complete task
7. **Output Generation**: Results printed to stdout

#### Step 3: Process Management
```bash
PID1=$!    # Capture process ID
wait $PID1 # Wait for completion
```

### Memory and Performance Characteristics

#### Memory Usage per Agent
- **Base memory**: ~50-100MB for Python + AI Coder core
- **Context memory**: Varies based on conversation history
- **Plugin memory**: Additional for loaded plugins
- **Tool execution**: Temporary spikes during tool calls

#### Performance Considerations

**Startup Time**: Each agent has full AI Coder startup overhead
- Plugin loading: ~0.1-0.5 seconds per plugin
- Context initialization: ~0.1 seconds
- Total per agent: ~1-3 seconds

**Execution Time**: Varies by task complexity
- Simple file reads: 2-5 seconds
- Complex analysis: 10-30 seconds
- API calls: Dependent on external response times

**Parallel Scaling**: Linear scaling for CPU-bound tasks
- 4 agents ≈ 4x faster than sequential
- Limited by API rate limits and memory

### Error Handling Patterns

#### Process-Level Errors

```bash
# Individual agent failure handling
echo "task" | python main.py > output.txt 2>&1 &
AGENT_PID=$!

# Wait with timeout and error checking
if timeout 60s bash -c "wait $AGENT_PID"; then
    echo "Agent completed successfully"
else
    echo "Agent failed or timed out"
fi
```

#### API-Level Errors

```bash
# Configure retries for reliability
export MAX_RETRIES=10

# Handle partial results in synthesis
if [ -f "output.txt" ] && [ -s "output.txt" ]; then
    echo "=== Results ===" >> combined.txt
    cat output.txt >> combined.txt
else
    echo "=== Agent Failed ===" >> combined.txt
    echo "No results available" >> combined.txt
fi
```

### Advanced Techniques

#### Dynamic Agent Generation

```bash
# Generate agents from file list
agents=()
for file in $(find . -name "*.py" -type f | head -5); do
    echo "Analyze $file for security issues" | python main.py > "sec_$(basename $file)" &
    agents+=($!)
done

# Wait for all agents
for pid in "${agents[@]}"; do
    wait $pid
done
```

#### Hierarchical Workflows

```bash
# Level 1: Data collection
echo "Extract all API endpoints" | python main.py > endpoints.txt &
echo "Find all database connections" | python main.py > db_connections.txt &
wait

# Level 2: Analysis (depends on Level 1 results)
echo "Analyze security of these endpoints: $(cat endpoints.txt)" | python main.py > endpoint_security.txt &
echo "Analyze security of these DB connections: $(cat db_connections.txt)" | python main.py > db_security.txt &
wait

# Level 3: Synthesis
echo "Create security report from: $(cat endpoint_security.txt) $(cat db_security.txt)" | python main.py > final_report.txt
```

#### Conditional Agent Execution

```bash
# Launch first agent
echo "Initial analysis" | python main.py > analysis.txt &
wait

# Check results and conditionally launch more
if grep -q "critical issue" analysis.txt; then
    echo "Deep security scan needed" | python main.py > deep_scan.txt &
    wait
fi
```

### Debugging Parallel Execution

#### Process Monitoring

```bash
# Monitor all AI Coder processes
ps aux | grep "python main.py" | grep -v grep

# Monitor file creation
watch -n 1 "ls -la /tmp/subagent_*/"
```

#### Logging Strategy

```bash
# Each agent gets its own log
echo "task" | python main.py > output.txt 2> error.log &

# Central logging
echo "[$(date)] Launching agent for: $task" >> orchestrator.log
```

#### Result Validation

```bash
# Check if agent produced valid results
validate_result() {
    local file="$1"
    
    if [ ! -f "$file" ]; then
        echo "ERROR: No output file created"
        return 1
    fi
    
    if [ ! -s "$file" ]; then
        echo "ERROR: Output file is empty"
        return 1
    fi
    
    if ! grep -q "AI:" "$file"; then
        echo "WARNING: No AI response found in output"
        return 1
    fi
    
    return 0
}
```

### Optimization Strategies

#### Resource Pooling

```bash
# Limit concurrent agents
MAX_AGENTS=3
agent_count=0

for task in "${tasks[@]}"; do
    # Wait if we've hit the limit
    if [ $agent_count -ge $MAX_AGENTS ]; then
        wait -n  # Wait for any agent to finish
        agent_count=$((agent_count - 1))
    fi
    
    # Launch new agent
    echo "$task" | python main.py > "result_$agent_count.txt" &
    agent_count=$((agent_count + 1))
done
```

#### Caching Results

```bash
# Check for cached results
cached_result="/tmp/cache/$(echo "$task" | md5sum | cut -d' ' -f1).txt"

if [ -f "$cached_result" ]; then
    echo "Using cached result for: $task"
    cp "$cached_result" "result.txt"
else
    echo "Computing result for: $task"
    echo "$task" | python main.py > "result.txt"
    mkdir -p /tmp/cache
    cp "result.txt" "$cached_result"
fi
```

### Security Considerations

#### Process Isolation
- Each agent runs in separate process space
- File system access controlled by `MINI_SANDBOX` setting
- Network access controlled by plugins and `YOLO_MODE`

#### Input Sanitization
```bash
# Sanitize task input before processing
sanitize_task() {
    local task="$1"
    # Remove dangerous shell metacharacters
    echo "$task" | sed 's/[;&|`$(){}[\]]//g'
}
```

#### Output Validation
- Check for sensitive data in results
- Validate file paths and permissions
- Monitor for unauthorized tool usage

### Integration Points

#### With Plugin System
- Agents can enable/disable plugins per task
- Custom plugins for agent-specific tools
- Plugin hooks for agent lifecycle management

#### With Socket API
- Remote agent orchestration via socket
- Agent status monitoring
- Result streaming instead of file-based

#### With Skills System
- Pre-defined agent types as skills
- Agent composition patterns
- Reusable agent workflows

This implementation guide provides the technical foundation for building sophisticated multi-agent systems using AI Coder's simple but powerful architecture.