# Subagent Guidelines and Best Practices

## 🔍 Important: Use Safe Temporary Directories

**ALWAYS use temporary directories for subagent outputs.** Never output files to the project root directory.

### Preferred Temporary Directory Strategy

1. **System Temp Directory** (Preferred):
   ```bash
   TEMP_DIR="/tmp/subagent_task_$(date +%s)"
   mkdir -p "$TEMP_DIR"
   ```

2. **AI Coder Temp Directory** (If system temp not accessible):
   ```bash
   TEMP_DIR="./aicoder/tmp/subagent_task_$(date +%s)"
   mkdir -p "$TEMP_DIR"
   ```

3. **User Temp Directory** (If available):
   ```bash
   TEMP_DIR="$HOME/tmp/subagent_task_$(date +%s)"
   mkdir -p "$TEMP_DIR"
   ```

**NEVER** use the project root (`./`) or current directory for subagent outputs. This clutters the project and risks overwriting important files.

## 🚫 What NOT to Do

### ❌ Bad Practices
- Outputting to project root: `python main.py > results.txt`
- Using fixed filenames: `python main.py > /tmp/output.txt`
- Overwriting existing files: Use unique timestamps
- Leaving temp files behind: Clean up after completion

### ✅ Good Practices
- Use unique timestamped directories
- Clean up temp files after use
- Use descriptive output names
- Check for existing files before creating

## 📝 Script Structure Template

### Safe Template
```bash
#!/bin/bash
set -e

# Global settings for subagents
export YOLO_MODE=1
export MINI_SANDBOX=0
export MAX_RETRIES=10

# SAFE TEMP DIRECTORY CREATION
TEMP_DIR="/tmp/subagent_task_$(date +%s)"
mkdir -p "$TEMP_DIR"

# Your subagent logic here
echo "task" | python main.py > "$TEMP_DIR/output.txt"

# Cleanup when done
cleanup() {
    rm -rf "$TEMP_DIR"
}
```

## 🧹 Cleanup Strategies

### Automatic Cleanup
```bash
# Add cleanup function
cleanup_temp() {
    echo "Cleaning up $TEMP_DIR..."
    rm -rf "$TEMP_DIR"
    echo "✅ Cleanup completed"
}

# Call cleanup at script end
cleanup_temp
```

### Manual Cleanup
```bash
# Inform user of location and provide cleanup command
echo "Temp files in: $TEMP_DIR"
echo "To cleanup: rm -rf $TEMP_DIR"
```

### Conditional Cleanup
```bash
# Allow user to keep results if needed
AUTO_CLEANUP=${AUTO_CLEANUP:-0}

if [ "$AUTO_CLEANUP" = "1" ]; then
    rm -rf "$TEMP_DIR"
else
    echo "Results kept in: $TEMP_DIR"
    echo "Set AUTO_CLEANUP=1 to auto-cleanup"
fi
```

## 🛡️ File Safety

### Prevent Overwrites
```bash
# Check if file exists before creating
OUTPUT_FILE="$TEMP_DIR/results.txt"
if [ -f "$OUTPUT_FILE" ]; then
    OUTPUT_FILE="$TEMP_DIR/results_$(date +%s).txt"
fi
```

### Use Unique Names
```bash
# Task-specific naming
"$TEMP_DIR/security_analysis.txt"
"$TEMP_DIR/performance_review.txt"
"$TEMP_DIR/api_documentation.txt"
```

## 📊 Output Management

### File Organization
```bash
# Organized temp directory structure
TEMP_DIR="/tmp/subagent_analysis_$(date +%s)"
mkdir -p "$TEMP_DIR"/{data,analysis,results}
```

### Result Validation
```bash
# Check if outputs were created successfully
validate_outputs() {
    for file in "$TEMP_DIR"/*.txt; do
        if [ -f "$file" ] && [ -s "$file" ]; then
            echo "✅ $(basename "$file"): Success"
        else
            echo "❌ $(basename "$file"): Failed"
        fi
    done
}
```

## ⏱️ Timeout Guidelines

When calling subagent scripts via `run_shell_command`, use generous timeouts:

- **2-4 agents**: 180-300 seconds
- **5-10 agents**: 300-600 seconds  
- **Complex workflows**: 600-900 seconds
- **Large codebases**: 900-1800 seconds

## 🔄 Error Handling

### Graceful Degradation
```bash
# Handle partial failures
successful_agents=0
total_agents=4

if [ -f "$TEMP_DIR/output1.txt" ]; then
    successful_agents=$((successful_agents + 1))
fi

echo "$successful_agents/$total_agents agents completed successfully"
```

### Retry Logic
```bash
# Retry failed agents individually
if [ ! -f "$TEMP_DIR/security_analysis.txt" ]; then
    echo "Retrying security analysis..."
    echo "Security analysis task" | python main.py > "$TEMP_DIR/security_analysis.txt"
fi
```

## 📡 User Communication

### Always Inform User
When launching subagents, always tell the user:
- Number of agents being launched
- Purpose of each agent
- Where results will be stored
- Estimated completion time
- How to access results

**Example:**
> "Launching 4 subagents in parallel:
> - Security Agent: Analyzing vulnerabilities and authentication
> - Performance Agent: Identifying bottlenecks and optimizations
> - Documentation Agent: Generating API and setup guides  
> - Testing Agent: Reviewing test coverage and quality
>
> Results will be saved to: /tmp/subagent_review_1703123456
> Estimated completion: 3-4 minutes"

## 🎯 Performance Optimization

### Memory Management
```bash
# Estimate memory per agent (~200MB)
AVAILABLE_MEMORY=$(free -m | awk '/^Mem:/{print $7}')
MAX_AGENTS=$((AVAILABLE_MEMORY / 200))

if [ $# -gt $MAX_AGENTS ]; then
    echo "⚠️  Reducing agents to $MAX_AGENTS due to memory limits"
    # Limit parallel execution
fi
```

### Staggered Launches
```bash
# Avoid API rate limits
for task in "${tasks[@]}"; do
    echo "$task" | python main.py > "$TEMP_DIR/task_$i.txt" &
    sleep 2  # Stagger launches
done
```

## 🔧 Environment Variables

### Required Settings
```bash
export YOLO_MODE=1        # Auto-approve tool actions
export MINI_SANDBOX=0     # Full file access
export MAX_RETRIES=10       # Handle API issues
```

### Optional Performance Settings
```bash
export CONTEXT_SIZE=32000          # Smaller context = faster
export STREAMING_TIMEOUT=120       # Longer timeouts
export STREAMING_READ_TIMEOUT=30  # Per-read timeout
```

These guidelines ensure safe, reliable, and clean subagent execution that doesn't interfere with the project or system stability.