# AI Coder Subagent System

> **Simple but powerful parallel AI execution using just bash scripts and environment variables**

## 🎯 Quick Start

```bash
# Basic parallel agents
echo "Analyze security" | python main.py > security.txt &
echo "Analyze performance" | python main.py > performance.txt &
wait

# Read results
echo "=== Security Analysis ==="
cat security.txt | tail -5
echo "=== Performance Analysis ==="  
cat performance.txt | tail -5
```

## 📚 Documentation

| Document | Purpose | For |
|----------|---------|-----|
| [README.md](./README.md) | **Core Concepts & Architecture** | Understanding how it works |
| [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) | **Technical Deep Dive** | Advanced implementation details |
| [RECIPES.md](./RECIPES.md) | **Ready-to-Use Scripts** | Quick copy-paste solutions |
| [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) | **Problem Solving** | Debugging and fixes |

## 🚀 Key Features

### ✅ No Infrastructure Required
- Uses AI Coder's existing architecture
- Pure bash + environment variables
- No additional dependencies

### ✅ Agent Specialization
```bash
AICODER_SYSTEM_PROMPT="You are a SECURITY EXPERT..." \
echo "Analyze security" | python main.py > security.txt &
```

### ✅ True Parallelism
```bash
# Launch 10 agents simultaneously
for i in {1..10}; do
    echo "Task $i" | python main.py > result_$i.txt &
done
wait
```

### ✅ Robust Orchestration
- Process management with `wait` and PID tracking
- Error handling and retries
- Result aggregation and synthesis

## 🔧 Core Configuration

```bash
# Required for automation
export YOLO_MODE=1        # Auto-approve tool actions
export MINI_SANDBOX=0     # Full file access
export MAX_RETRIES=10     # Handle API issues

# Optional: Custom prompts
AICODER_SYSTEM_PROMPT="You are a SPECIALIST..."

# Optional: Performance tuning
export CONTEXT_SIZE=32000
export STREAMING_TIMEOUT=60
```

## 📊 Example Use Cases

### Code Review with Multiple Perspectives
```bash
# Security expert
AICODER_SYSTEM_PROMPT="SECURITY REVIEWER..." \
echo "Review for security issues" | python main.py > security.txt &

# Performance expert  
AICODER_SYSTEM_PROMPT="PERFORMANCE REVIEWER..." \
echo "Review for performance issues" | python main.py > performance.txt &

# Code quality expert
AICODER_SYSTEM_PROMPT="QUALITY REVIEWER..." \
echo "Review for code quality" | python main.py > quality.txt &

wait  # Wait for all reviews

# Synthesize comprehensive report
cat > full_review.md << EOF
# Code Review Report

## Security Analysis
$(cat security.txt)

## Performance Analysis  
$(cat performance.txt)

## Quality Analysis
$(cat quality.txt)
EOF
```

### Parallel Documentation Generation
```bash
# API docs
echo "Extract and document all APIs" | python main.py > api_docs.txt &
# Architecture docs  
echo "Document architecture patterns" | python main.py > arch_docs.txt &
# Setup docs
echo "Document installation and setup" | python main.py > setup_docs.txt &
wait

# Combine
cat api_docs.txt arch_docs.txt setup_docs.txt > complete_docs.md
```

### Multi-File Analysis
```bash
# Process all Python files in parallel
for file in *.py; do
    echo "Analyze $file for issues" | python main.py > "analysis_$(basename $file)" &
done
wait

# Summary
echo "Analysis completed for $(ls analysis_*.txt | wc -l) files"
```

## 🎯 Real-World Applications

### 1. Comprehensive Security Audit
- Parallel analysis: authentication, input validation, dependencies
- Automated vulnerability scanning
- Risk assessment report generation

### 2. Performance Optimization
- Parallel profiling of different components
- Bottleneck identification
- Optimization recommendations

### 3. Code Quality Assessment
- Multiple coding standards checks
- Maintainability analysis
- Technical debt identification

### 4. Documentation Generation
- API reference extraction
- Architecture documentation
- User guide creation

### 5. Research & Analysis
- Multiple source research in parallel
- Synthesis of findings
- Comprehensive report generation

## 🔍 How It Works (5-Second Explanation)

```
Bash Script → Environment Variables → Stdin → python main.py → Tools → File Output
     ↓                    ↓              ↓           ↓        ↓         ↓
Configure           AICODER_...      Non-interactive  Agent    Built-in   Results
Settings            Config           Mode             Runs     Tools      Captured
```

**Key Insight**: Each agent gets its own process, environment, and output file - completely isolated but coordinated through shell scripting.

## 🛠️ Available Scripts

In the main project directory:

| Script | Purpose |
|--------|---------|
| `launch_subagents.sh` | Basic 4-agent parallel launcher |
| `subagent_orchestrator.sh` | Advanced 5-agent + synthesis workflow |
| `subagent_runner.sh` | Utility for arbitrary parallel tasks |

## 🎉 Benefits Over Alternatives

| Traditional Approach | Subagent System |
|----------------------|-----------------|
| Complex infrastructure | Simple bash scripts |
| External orchestration tools | Built-in process management |
| Network communication | File-based I/O |
| Complex setup | Zero additional dependencies |
| Learning curve | Familiar shell scripting |

## 🚦 When to Use Subagents

### ✅ Perfect For:
- **Parallel analysis** of the same codebase
- **Multi-perspective reviews** (security, performance, quality)
- **Batch processing** of multiple files/tasks
- **Automated documentation generation**
- **Research and synthesis** tasks

### ❌ Not Ideal For:
- **Agent-to-agent real-time communication** (no built-in messaging)
- **Complex workflow dependencies** (use sequential orchestration)
- **Large-scale distributed computing** (use dedicated frameworks)
- **State sharing between agents** (files work but are limited)

## 🔄 Future Evolution

The subagent system could evolve into:

### Core Skill Integration
- `/subagents launch "task1" "task2" "task3"`
- Predefined agent types and workflows
- Built-in result synthesis

### Advanced Orchestration
- Workflow definitions in YAML
- Conditional agent spawning
- Dynamic task allocation

### Enhanced Communication
- Agent-to-agent messaging via sockets
- Shared state management
- Real-time result streaming

## 🤝 Contributing

The subagent system demonstrates how AI Coder's architecture enables sophisticated patterns without complexity. To extend:

1. **New Agent Types**: Create specialized prompts and configurations
2. **Workflow Patterns**: Document and share new orchestration approaches  
3. **Tool Integration**: Extend agents with custom tools via plugins
4. **Performance Optimization**: Share tuning and scaling techniques

---

**Bottom Line**: The subagent system gives you multi-agent AI capabilities with the simplicity of shell scripting. No complex infrastructure, just powerful parallel processing.

📖 **Start with [RECIPES.md](./RECIPES.md) for ready-to-use examples!**