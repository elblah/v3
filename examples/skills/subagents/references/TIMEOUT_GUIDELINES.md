# Timeout Guidelines for Subagent Execution

## ⏱️ Why Generous Timeouts Matter

Subagent scripts run multiple AI processes in parallel. Each process needs time for:
- **AI startup and initialization** (~2-5 seconds)
- **Tool execution and API calls** (variable, 10-120 seconds)
- **Result processing and output** (~1-3 seconds)
- **Network latency and retries** (variable)

Without generous timeouts, `run_shell_command` will kill subagent processes before they complete, leading to failed analyses and wasted work.

## 📊 Recommended Timeout Matrix

| Agent Count | Task Complexity | Recommended Timeout | Reason |
|-------------|----------------|-------------------|---------|
| 2-4 agents | Simple (file reading, basic analysis) | 180-300s (3-5 min) | Basic parallel tasks |
| 2-4 agents | Medium (code review, documentation) | 300-600s (5-10 min) | Moderate complexity |
| 5-10 agents | Simple-Medium | 300-600s (5-10 min) | More processes need more time |
| 5-10 agents | Complex (security audit, performance) | 600-900s (10-15 min) | Complex analysis × parallel |
| 10+ agents | Any complexity | 600-900s (10-15 min) | Maximum parallel overhead |
| Large codebases (>10k files) | Any complexity | 900-1800s (15-30 min) | Volume requires time |
| Hierarchical workflows | Multi-phase | 900-1800s (15-30 min) | Sequential phases need time |

## 🎯 Timeout by Task Type

### Quick Tasks (30-60 seconds per agent)
- File content analysis
- Simple grep searches
- Basic file operations
- Configuration analysis

### Medium Tasks (60-180 seconds per agent)  
- Code structure analysis
- API documentation generation
- Basic security review
- Performance profiling

### Complex Tasks (180-600 seconds per agent)
- Comprehensive security audit
- Multi-perspective code review
- Architecture documentation
- Risk assessment

### Expert Tasks (300-900 seconds per agent)
- Multi-phase analysis workflows
- Competitive solution generation
- Comprehensive testing review
- Enterprise-level assessment

## ⚙️ Using Timeouts Correctly

### When Calling Subagent Scripts
```bash
# Basic parallel analysis
run_shell_command "./examples/skills/subagents/scripts/launch_basic.sh" timeout=300

# Complex code review  
run_shell_command "./examples/skills/subagents/scripts/code_review.sh" timeout=600

# Comprehensive analysis workflow
run_shell_command "./examples/skills/subagents/scripts/comprehensive_analysis.sh" timeout=900

# Large codebase analysis
run_shell_command "./examples/skills/subagents/scripts/comprehensive_analysis.sh" timeout=1800
```

### Dynamic Timeout Calculation
```bash
# Calculate based on agent count and complexity
calculate_timeout() {
    local agent_count=$1
    local complexity=${2:-medium}  # simple, medium, complex, expert
    
    local base_timeout
    
    case $complexity in
        simple)   base_timeout=60 ;;
        medium)   base_timeout=180 ;;
        complex)   base_timeout=300 ;;
        expert)    base_timeout=600 ;;
    esac
    
    # Scale by agent count (diminishing returns)
    if [ $agent_count -le 4 ]; then
        echo $base_timeout
    elif [ $agent_count -le 10 ]; then
        echo $((base_timeout * 2))
    else
        echo $((base_timeout * 3))
    fi
}

# Usage
TIMEOUT=$(calculate_timeout $# "medium")
echo "Using timeout: $TIMEOUT seconds"
```

## 🚫 What Happens with Insufficient Timeouts

### Too Short (under 60 seconds)
- **Symptoms**: Agents killed mid-analysis, partial results, empty files
- **Impact**: Failed subagents, incomplete synthesis, wasted computation
- **Fix**: Increase to minimum 180 seconds for any parallel work

### Marginal (60-180 seconds)  
- **Symptoms**: Some agents succeed, others timeout unpredictably
- **Impact**: Inconsistent results, retry loops, user confusion
- **Fix**: Use task-appropriate timeouts from matrix above

### Good (180+ seconds)
- **Symptoms**: Consistent completions, reliable results, happy users
- **Impact**: Successful analyses, comprehensive results, efficient workflow

## 📋 Implementation Checklist

Before running subagent scripts, verify:

- [ ] **Agent count known**: Count how many agents will launch
- [ ] **Task complexity assessed**: Simple/medium/complex/expert
- [ ] **Timeout selected**: Use matrix or calculation
- [ ] **Buffer added**: Add 20-30% extra for safety
- [ ] **Fallback planned**: What happens if some agents fail
- [ ] **User informed**: Tell user expected completion time

### Example User Communication
> "Launching 6 subagents for comprehensive security audit"
> "Task complexity: Expert-level analysis"
> "Estimated completion: 10-12 minutes"
> "Timeout: 900 seconds configured"
> "Results location: /tmp/subagent_security_1703123456"

## 🔄 Progressive Timeout Strategy

### Start Conservative, Scale if Needed
```bash
# First attempt with conservative timeout
run_shell_command "./code_review.sh" timeout=300

# Check if completed successfully
if [ $? -ne 0 ]; then
    echo "⚠️  First attempt timed out, retrying with extended timeout..."
    run_shell_command "./code_review.sh" timeout=600
fi
```

### Monitor and Adapt
```bash
# Monitor completion times
start_time=$(date +%s)
run_shell_command "./parallel_runner.sh \"task1\" \"task2\" \"task3\"" timeout=600
end_time=$(date +%s)
duration=$((end_time - start_time))

echo "Completed in $duration seconds"
if [ $duration -gt 450 ]; then
    echo "⚠️  Consider increasing timeout for similar tasks"
fi
```

## 💡 Pro Tips

### Buffer Rule
> **Always add 20-30% buffer** to calculated timeouts. Network issues, API delays, and complex outputs require extra time.

### Agent Count vs Time
> **More agents = more overhead**. Double the timeout when going from 4 to 8 agents, triple when going above 10.

### Task Complexity Trumps Count
> **Complex tasks need more time**. A security audit with 2 agents may need more time than simple analysis with 6 agents.

### Error Recovery
> **Failed agents waste time**. It's better to use a generous timeout and have everything complete than to retry multiple times.

Following these timeout guidelines ensures reliable subagent execution and successful analysis workflows.