# Subagent System Troubleshooting Guide

## Common Issues and Solutions

### 1. Agents Not Starting

**Symptoms**:
- No output files created
- Script completes immediately
- No processes running

**Common Causes**:

#### Missing Environment Variables
```bash
# Check if required variables are set
env | grep -E "(YOLO_MODE|MINI_SANDBOX|TOOLS_ALLOW|API_|OPENAI_)"

# Fix: Set required variables
export YOLO_MODE=1
export MINI_SANDBOX=0
# Optional: Restrict tool access for subagents
# export TOOLS_ALLOW="read_file,grep,list_directory"  # Read-only access
export API_BASE_URL="https://your-api.com/v1"
export API_KEY="your-key"
```

#### Python Path Issues
```bash
# Check if python main.py works directly
echo "test" | python main.py

# Fix: Ensure you're in the correct directory
cd /path/to/aicoder
echo "test" | python main.py
```

#### Permission Issues
```bash
# Check file permissions
ls -la main.py
chmod +x main.py

# Check output directory permissions
mkdir -p /tmp/test_output
touch /tmp/test_output/test.txt
```

### 2. Agents Hanging or Timing Out

**Symptoms**:
- Processes running indefinitely
- No output after long time
- `wait` command never returns

**Solutions**:

#### Use Per-Agent Timeouts
```bash
# Bad: No timeout
echo "task" | python main.py > output.txt &

# Good: With timeout
timeout 60s bash -c 'echo "task" | python main.py > output.txt' &
```

#### Configure Global Timeouts
```bash
export TOTAL_TIMEOUT=120      # 120 seconds total
```

#### Implement Retry Logic
```bash
run_with_retry() {
    local task="$1"
    local output="$2"
    local retries=3
    local delay=5
    
    for ((i=1; i<=retries; i++)); do
        echo "Attempt $i: $task"
        if timeout 60s bash -c "echo '$task' | python main.py > '$output'"; then
            echo "Success on attempt $i"
            return 0
        fi
        echo "Attempt $i failed, retrying in ${delay}s..."
        sleep $delay
        delay=$((delay * 2))  # Exponential backoff
    done
    
    echo "All attempts failed for: $task"
    return 1
}
```

### 3. API Rate Limiting

**Symptoms**:
- Intermittent failures
- HTTP 429 errors
- "Too many requests" messages

**Solutions**:

#### Configure Retry Settings
```bash
export MAX_RETRIES=10  # Increase retries
export YOLO_MODE=1     # Auto-retry on failures
```

#### Stagger Agent Launches
```bash
# Bad: All agents start at once
for task in "${tasks[@]}"; do
    echo "$task" | python main.py > "result_$i.txt" &
done

# Good: Staggered launches
for i in "${!tasks[@]}"; do
    echo "${tasks[$i]}" | python main.py > "result_$i.txt" &
    sleep 2  # Stagger by 2 seconds
done
```

#### Limit Concurrent Agents
```bash
MAX_AGENTS=3
current_agents=0

for task in "${tasks[@]}"; do
    # Wait if at limit
    while [ $current_agents -ge $MAX_AGENTS ]; do
        wait -n  # Wait for any agent to finish
        current_agents=$((current_agents - 1))
    done
    
    # Launch new agent
    echo "$task" | python main.py > "result_$current_agents.txt" &
    current_agents=$((current_agents + 1))
done
```

### 4. Memory Issues

**Symptoms**:
- System becomes sluggish
- Out of memory errors
- Processes killed by OOM killer

**Solutions**:

#### Monitor Memory Usage
```bash
# Monitor AI Coder processes
watch -n 2 'ps aux | grep "python main.py" | grep -v grep | awk "{print \$2, \$4, \$11}"'

# Check system memory
free -h
```

#### Limit Agent Count
```bash
# Calculate safe agent count based on memory
AVAILABLE_MEMORY=$(free -g | awk '/^Mem:/{print $7}')
MEMORY_PER_AGENT=200  # Estimate 200MB per agent
MAX_AGENTS=$((AVAILABLE_MEMORY * 1024 / MEMORY_PER_AGENT))

echo "Safe to run $MAX_AGENTS agents concurrently"
```

#### Use Smaller Context for Agents
```bash
export CONTEXT_SIZE=32000  # Reduce from default 128k
export CONTEXT_COMPACT_PERCENTAGE=50  # Compact at 50%
```

### 5. File System Issues

**Symptoms**:
- Permission denied errors
- Disk space full
- Files not created

**Solutions**:

#### Check Disk Space
```bash
df -h
df -h /tmp  # Check temp directory
```

#### Fix Permissions
```bash
# Create output directory with proper permissions
mkdir -p /tmp/subagent_output
chmod 755 /tmp/subagent_output

# Run as current user if having permission issues
echo "task" | python main.py > output.txt
```

#### Use Alternative Output Directory
```bash
# Use user home directory instead of /tmp
OUTPUT_DIR="$HOME/subagent_results"
mkdir -p "$OUTPUT_DIR"
echo "task" | python main.py > "$OUTPUT_DIR/result.txt"
```

### 6. Plugin-Related Issues

**Symptoms**:
- Agents failing with plugin errors
- Inconsistent behavior between agents
- Tools not available

**Solutions**:

#### Disable Problematic Plugins
```bash
# Run without specific plugins
echo "task" | python main.py --disable-plugin web_search > result.txt &
```

#### Use Minimal Plugin Set
```bash
# Only load essential plugins
export AICODER_PLUGINS="shell,skills"
echo "task" | python main.py > result.txt &
```

#### Check Plugin Loading
```bash
# Debug plugin loading
export DEBUG=1
echo "task" | python main.py > debug_output.txt 2>&1 &
cat debug_output.txt | grep -i plugin
```

## Debugging Tools and Techniques

### Process Monitoring

```bash
# Monitor all AI Coder processes
ps aux | grep "python main.py"

# Monitor specific process
strace -p <PID> 2>&1 | grep -E "(read|write|exec)"

# Monitor file activity
inotifywait -m /tmp/subagent_output/
```

### Logging

```bash
# Enable debug logging
export DEBUG=1

# Create per-agent logs
echo "task" | python main.py > result.txt 2>agent_$(date +%s).log &

# Central logging
exec 1> >(tee -a orchestrator.log)
exec 2> >(tee -a orchestrator.log >&2)
```

### Result Validation

```bash
validate_output() {
    local file="$1"
    local min_size=100  # Minimum bytes
    
    if [ ! -f "$file" ]; then
        echo "ERROR: File not created: $file"
        return 1
    fi
    
    if [ ! -s "$file" ]; then
        echo "ERROR: File is empty: $file"
        return 1
    fi
    
    if [ $(stat -f%z "$file" 2>/dev/null || stat -c%s "$file") -lt $min_size ]; then
        echo "WARNING: File too small: $file"
    fi
    
    if ! grep -q "AI:" "$file" 2>/dev/null; then
        echo "WARNING: No AI response found in: $file"
    fi
    
    return 0
}

# Usage
for file in result_*.txt; do
    validate_output "$file"
done
```

## Performance Tuning

### Optimize for Speed

```bash
# Increase timeouts for faster completion
export TOTAL_TIMEOUT=60

# Use faster model if available
export API_MODEL="faster-model"

# Reduce context for quicker processing
export CONTEXT_SIZE=16000
```

### Optimize for Reliability

```bash
# Increase reliability settings
export MAX_RETRIES=10
export YOLO_MODE=1

# Add delays between agent launches
sleep 1  # Between launches
```

### Optimize for Memory

```bash
# Reduce memory usage
export CONTEXT_SIZE=32000
export CONTEXT_COMPACT_PERCENTAGE=25

# Limit agent pool size
MAX_AGENTS=2
```

## Recovery Procedures

### When All Agents Fail

```bash
#!/bin/bash
# emergency_recovery.sh

# Kill all hanging AI Coder processes
pkill -f "python main.py"

# Clean up output directory
rm -rf /tmp/subagent_*
mkdir -p /tmp/subagent_recovery

# Try with minimal settings
export YOLO_MODE=1
export MINI_SANDBOX=0
export DEBUG=1

# Test single agent first
echo "test" | python main.py > /tmp/subagent_recovery/test.txt

if [ -s "/tmp/subagent_recovery/test.txt" ]; then
    echo "✅ Basic functionality works"
else
    echo "❌ Basic functionality broken"
    exit 1
fi

echo "Recovery complete, try again with reduced agent count"
```

### Partial Result Recovery

```bash
#!/bin/bash
# partial_recovery.sh

OUTPUT_DIR="/tmp/subagent_run_*"

# Find most recent run
LATEST_RUN=$(ls -td /tmp/subagent_run_* 2>/dev/null | head -1)

if [ -z "$LATEST_RUN" ]; then
    echo "No previous runs found"
    exit 1
fi

echo "Recovering from: $LATEST_RUN"

# Check what we have
echo "Existing results:"
for file in "$LATEST_RUN"/*.txt; do
    if [ -s "$file" ]; then
        echo "✅ $(basename "$file") ($(wc -c < "$file") bytes)"
    else
        echo "❌ $(basename "$file") (empty/missing)"
    fi
done

# Generate partial report
cat > "$LATEST_RUN/partial_report.txt" << EOF
# Partial Analysis Report

## Completed Analyses
$(for file in "$LATEST_RUN"/*.txt; do
    if [ -s "$file" ]; then
        echo "### $(basename "$file" .txt)"
        tail -5 "$file"
        echo ""
    fi
done)

## Missing Analyses
$(for file in "$LATEST_RUN"/*.txt; do
    if [ ! -s "$file" ]; then
        echo "- $(basename "$file" .txt)"
    fi
done)

Generated on: $(date)
EOF

echo "Partial report: $LATEST_RUN/partial_report.txt"
```

## Prevention Strategies

### Pre-Launch Checklist

```bash
pre_launch_check() {
    echo "🔍 Pre-launch checks..."
    
    # Check API connectivity
    if ! echo "test" | python main.py >/dev/null 2>&1; then
        echo "❌ API connectivity failed"
        return 1
    fi
    
    # Check available memory
    if [ $(free -m | awk '/^Mem:/{print $7}') -lt 1000 ]; then
        echo "⚠️  Low memory available"
    fi
    
    # Check disk space
    if [ $(df /tmp | tail -1 | awk '{print $4}') -lt 1000 ]; then
        echo "⚠️  Low disk space in /tmp"
    fi
    
    # Check environment
    if [ -z "$API_BASE_URL" ]; then
        echo "❌ API_BASE_URL not set"
        return 1
    fi
    
    echo "✅ Pre-launch checks passed"
    return 0
}
```

### Resource Monitoring During Execution

```bash
monitor_resources() {
    local duration=$1
    local interval=$2
    
    for ((i=0; i<duration; i+=interval)); do
        echo "$(date): Memory: $(free -m | awk '/^Mem:/{print $3}'MB used, $(ps aux | grep 'python main.py' | wc -l) agents running"
        sleep $interval
    done
}

# Usage
monitor_resources 300 10 &  # Monitor for 5 minutes, every 10 seconds
MONITOR_PID=$!

# Run your agents...
# ...

kill $MONITOR_PID  # Stop monitoring
```

### Restricting Subagent Tool Access

When launching subagents, you may want to limit their access to certain tools for security or safety reasons. Use the `TOOLS_ALLOW` environment variable:

```bash
# Launch a read-only analysis subagent
echo "Analyze the codebase" | \
TOOLS_ALLOW="read_file,grep,list_directory" \
$AICODER_CMD > analysis.txt &

# Launch a subagent that can only read and search
echo "Review code patterns" | \
TOOLS_ALLOW="read_file,grep" \
$AICODER_CMD > review.txt &

# Launch a subagent with full tool access (default)
echo "Make changes to code" | \
$AICODER_CMD > changes.txt &
```

**Use cases for restricted tool access:**

1. **Security Analysis**: Read-only access prevents accidental code modifications while reviewing for vulnerabilities
2. **Code Review**: Reviewers should only read code, not make changes
3. **Documentation Generation**: Only need read tools to inspect code for docs
4. **Research Tasks**: Inspect files without risk of modifications

**Available tools:**

| Tool | Description | Use Case |
|------|-------------|----------|
| `read_file` | Read file contents | Safe for all analysis |
| `grep` | Search text in files | Pattern finding |
| `list_directory` | List files and directories | Codebase exploration |
| `write_file` | Write/create files | Code generation tasks |
| `edit_file` | Edit files | Making targeted changes |
| `run_shell_command` | Execute shell commands | Build/test automation |

**Example: Read-only code review system:**
```bash
# Multiple reviewers, all read-only
echo "Check for security issues" | \
TOOLS_ALLOW="read_file,grep" \
AICODER_SYSTEM_PROMPT="You are a security reviewer. Identify vulnerabilities." \
$AICODER_CMD > security_review.txt &

echo "Check for performance issues" | \
TOOLS_ALLOW="read_file,grep" \
AICODER_SYSTEM_PROMPT="You are a performance reviewer. Identify bottlenecks." \
$AICODER_CMD > performance_review.txt &

wait
```

This troubleshooting guide provides comprehensive solutions for common issues encountered when working with the subagent system.