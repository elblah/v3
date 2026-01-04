# Subagent Recipes and Patterns

## Quick Start Recipes

### Recipe 1: Basic Parallel Analysis

**Use Case**: Analyze the same codebase from different perspectives simultaneously.

```bash
#!/bin/bash
# recipe1_basic_analysis.sh

export YOLO_MODE=1
export MINI_SANDBOX=0

# Launch three expert analysts
echo "Analyze this codebase for security vulnerabilities and risks" | python main.py > security_report.txt &
echo "Analyze this codebase for performance bottlenecks and optimization opportunities" | python main.py > performance_report.txt &
echo "Analyze this codebase for code quality issues and maintainability concerns" | python main.py > quality_report.txt &

wait  # Wait for all to complete

echo "=== Security Analysis ==="
cat security_report.txt | tail -10

echo "=== Performance Analysis ==="
cat performance_report.txt | tail -10

echo "=== Quality Analysis ==="
cat quality_report.txt | tail -10
```

### Recipe 2: Documentation Generator

**Use Case**: Generate comprehensive documentation by analyzing different parts of codebase in parallel.

```bash
#!/bin/bash
# recipe2_docs_generator.sh

export YOLO_MODE=1
export MINI_SANDBOX=0

mkdir -p /tmp/generated_docs

# API Documentation
echo "Analyze all Python files and extract API endpoints, functions, and classes. Generate API documentation." | python main.py > /tmp/generated_docs/api_docs.txt &

# Architecture Documentation  
echo "Analyze the overall architecture, design patterns, and component relationships. Generate architecture documentation." | python main.py > /tmp/generated_docs/arch_docs.txt &

# Setup/Installation Documentation
echo "Analyze setup files, dependencies, and configuration. Generate installation and setup documentation." | python main.py > /tmp/generated_docs/setup_docs.txt &

# Usage Examples
echo "Analyze the codebase and extract usage examples, CLI commands, and common workflows." | python main.py > /tmp/generated_docs/usage_examples.txt &

wait

# Combine all documentation
cat > /tmp/generated_docs/COMPLETE_DOCUMENTATION.md << EOF
# Complete Documentation

## API Documentation
$(cat /tmp/generated_docs/api_docs.txt)

## Architecture Documentation  
$(cat /tmp/generated_docs/arch_docs.txt)

## Setup and Installation
$(cat /tmp/generated_docs/setup_docs.txt)

## Usage Examples
$(cat /tmp/generated_docs/usage_examples.txt)
EOF

echo "Documentation generated: /tmp/generated_docs/COMPLETE_DOCUMENTATION.md"
```

### Recipe 3: Code Review Assistant

**Use Case**: Comprehensive code review with multiple specialized reviewers.

```bash
#!/bin/bash
# recipe3_code_review.sh

export YOLO_MODE=1
export MINI_SANDBOX=0

REVIEW_DIR="/tmp/code_review_$(date +%s)"
mkdir -p "$REVIEW_DIR"

# Security Reviewer
AICODER_SYSTEM_PROMPT="You are a SECURITY REVIEWER. Focus only on security vulnerabilities, authentication issues, input validation, and potential attack vectors. Be specific and provide fixes." \
echo "Review the changes in the current codebase for security issues" | python main.py > "$REVIEW_DIR/security_review.txt" &

# Performance Reviewer
AICODER_SYSTEM_PROMPT="You are a PERFORMANCE REVIEWER. Focus only on performance issues, efficiency, resource usage, and scalability concerns." \
echo "Review the changes in the current codebase for performance issues" | python main.py > "$REVIEW_DIR/performance_review.txt" &

# Code Quality Reviewer
AICODER_SYSTEM_PROMPT="You are a CODE QUALITY REVIEWER. Focus only on code quality, maintainability, design patterns, and best practices." \
echo "Review the changes in the current codebase for code quality issues" | python main.py > "$REVIEW_DIR/quality_review.txt" &

# Testing Reviewer
AICODER_SYSTEM_PROMPT="You are a TESTING REVIEWER. Focus only on test coverage, test quality, edge cases, and testing strategies." \
echo "Review the changes in the current codebase for testing issues" | python main.py > "$REVIEW_DIR/testing_review.txt" &

wait

# Generate comprehensive review summary
cat > "$REVIEW_DIR/comprehensive_review.md" << EOF
# Comprehensive Code Review

## 🔒 Security Review
$(cat "$REVIEW_DIR/security_review.txt")

## ⚡ Performance Review  
$(cat "$REVIEW_DIR/performance_review.txt")

## 📊 Code Quality Review
$(cat "$REVIEW_DIR/quality_review.txt")

## 🧪 Testing Review
$(cat "$REVIEW_DIR/testing_review.txt")

## 📋 Summary
$(cat "$REVIEW_DIR/"*.txt | grep -E "(CRITICAL|HIGH|MEDIUM)" | sort | uniq -c)
EOF

echo "Code review completed: $REVIEW_DIR/comprehensive_review.md"
```

## Advanced Patterns

### Pattern 1: Adaptive Agent System

Agents that spawn other agents based on initial findings.

```bash
#!/bin/bash
# pattern1_adaptive.sh

export YOLO_MODE=1
export MINI_SANDBOX=0

# Phase 1: Initial broad analysis
echo "Do a quick scan of the codebase and identify areas that need deeper analysis. Focus on finding complexity, risk, or areas of concern." | python main.py > initial_scan.txt &

wait

# Phase 2: Parse initial scan for areas needing deep analysis
if grep -q "security" initial_scan.txt; then
    echo "Deep security analysis of identified areas" | python main.py > deep_security.txt &
fi

if grep -q "performance" initial_scan.txt; then
    echo "Deep performance analysis of identified bottlenecks" | python main.py > deep_performance.txt &
fi

if grep -q "complex" initial_scan.txt; then
    echo "Deep complexity analysis of identified areas" | python main.py > deep_complexity.txt &
fi

wait  # Wait for any spawned agents
```

### Pattern 2: Multi-Language Processing

Process codebases with multiple programming languages in parallel.

```bash
#!/bin/bash
# pattern2_multilang.sh

export YOLO_MODE=1
export MINI_SANDBOX=0

# Find files by language and process in parallel
echo "Analyze all Python files for Python-specific issues and patterns" | python main.py > python_analysis.txt &
echo "Analyze all JavaScript files for JavaScript-specific issues and patterns" | python main.py > javascript_analysis.txt &
echo "Analyze all configuration files (JSON, YAML, TOML) for structure and validity" | python main.py > config_analysis.txt &
echo "Analyze all documentation files (Markdown, README) for completeness and quality" | python main.py > docs_analysis.txt &

wait

# Synthesize multi-language report
cat > multilang_report.md << EOF
# Multi-Language Codebase Analysis

## Python Analysis
$(cat python_analysis.txt | tail -15)

## JavaScript Analysis  
$(cat javascript_analysis.txt | tail -15)

## Configuration Analysis
$(cat config_analysis.txt | tail -15)

## Documentation Analysis
$(cat docs_analysis.txt | tail -15)
EOF
```

### Pattern 3: Competitive Analysis

Have multiple agents approach the same problem with different strategies.

```bash
#!/bin/bash
# pattern3_competitive.sh

export YOLO_MODE=1
export MINI_SANDBOX=0

TASK="Generate the best possible documentation for this project"

# Different approaches
AICODER_SYSTEM_PROMPT="You are a TECHNICAL WRITER. Focus on detailed technical specifications, API references, and implementation details." \
echo "$TASK" | python main.py > tech_docs.txt &

AICODER_SYSTEM_PROMPT="You are a USER EXPERIENCE WRITER. Focus on user guides, tutorials, and making the project accessible to newcomers." \
echo "$TASK" | python main.py > user_docs.txt &

AICODER_SYSTEM_PROMPT="You are a DEVELOPER ADVOCATE. Focus on examples, code snippets, and demonstrating best practices." \
echo "$TASK" | python main.py > dev_docs.txt &

AICODER_SYSTEM_PROMPT="You are a PRODUCT MANAGER. Focus on features, benefits, and business value proposition." \
echo "$TASK" | python main.py > product_docs.txt &

wait

# Let AI judge the best approach
cat > judge_input.txt << EOF
You are a DOCUMENTATION EXPERT JUDGE. 
You have 4 different documentation approaches below. 
Analyze each and recommend the best approach or suggest how to combine the best elements.

=== TECHNICAL APPROACH ===
$(cat tech_docs.txt)

=== USER EXPERIENCE APPROACH ===  
$(cat user_docs.txt)

=== DEVELOPER ADVOCATE APPROACH ===
$(cat dev_docs.txt)

=== PRODUCT MANAGER APPROACH ===
$(cat product_docs.txt)

Provide your judgment and recommendations.
EOF

cat judge_input.txt | python main.py > final_recommendation.txt
```

## Production-Ready Templates

### Template 1: Scalable Agent Pool

```bash
#!/bin/bash
# template_scalable_pool.sh

export YOLO_MODE=1
export MINI_SANDBOX=0
MAX_CONCURRENT_AGENTS=4
TASK_TIMEOUT=120

# Agent pool management
agent_pids=()
active_agents=0

launch_agent() {
    local task="$1"
    local output_file="$2"
    
    # Wait if we're at capacity
    while [ $active_agents -ge $MAX_CONCURRENT_AGENTS ]; do
        # Check for completed agents
        for i in "${!agent_pids[@]}"; do
            pid="${agent_pids[$i]}"
            if ! kill -0 "$pid" 2>/dev/null; then
                # Agent completed
                unset agent_pids[$i]
                active_agents=$((active_agents - 1))
                break
            fi
        done
        sleep 1
    done
    
    # Launch new agent
    echo "$task" | timeout $TASK_TIMEOUT python main.py > "$output_file" 2>/dev/null &
    local new_pid=$!
    agent_pids+=("$new_pid")
    active_agents=$((active_agents + 1))
    
    echo "Launched agent (PID: $new_pid) for task: $task"
}

# Example usage
tasks=(
    "Analyze security"
    "Check performance" 
    "Review code quality"
    "Test coverage analysis"
    "Documentation check"
    "Dependency review"
    "Configuration audit"
    "Error handling review"
)

for i in "${!tasks[@]}"; do
    launch_agent "${tasks[$i]}" "result_$i.txt"
done

# Wait for remaining agents
for pid in "${agent_pids[@]}"; do
    wait "$pid" 2>/dev/null
done

echo "All agents completed"
```

### Template 2: Error-Resilient Workflow

```bash
#!/bin/bash
# template_error_resilient.sh

export YOLO_MODE=1
export MINI_SANDBOX=0
MAX_RETRIES=10

run_resilient_agent() {
    local task="$1"
    local output_file="$2"
    local retry_count=0
    
    while [ $retry_count -lt $MAX_RETRIES ]; do
        echo "Attempt $((retry_count + 1)): $task"
        
        if echo "$task" | python main.py > "$output_file" 2>/dev/null; then
            # Check if output is valid
            if [ -s "$output_file" ] && grep -q "AI:" "$output_file"; then
                echo "✅ Success: $task"
                return 0
            else
                echo "⚠️  Invalid output for: $task"
            fi
        else
            echo "❌ Failed: $task"
        fi
        
        retry_count=$((retry_count + 1))
        sleep $((retry_count * 2))  # Exponential backoff
    done
    
    echo "💀 Gave up on: $task (after $MAX_RETRIES attempts)"
    echo "FAILED: $task" > "$output_file"
    return 1
}

# Example usage
tasks=(
    "Complex security analysis"
    "Performance bottleneck identification" 
    "Architecture review"
    "Code quality assessment"
)

for i in "${!tasks[@]}"; do
    run_resilient_agent "${tasks[$i]}" "result_$i.txt" &
done

wait

echo "Resilient execution completed"
```

### Template 3: Result Aggregation

```bash
#!/bin/bash
# template_aggregation.sh

export YOLO_MODE=1
export MINI_SANDBOX=0

# Phase 1: Data collection
echo "Extract all metrics and measurements from the codebase" | python main.py > metrics.txt &
echo "Identify all technical debt and code issues" | python main.py > tech_debt.txt &
echo "Analyze all dependencies and their risks" | python main.py > dependencies.txt &
echo "Catalog all features and capabilities" | python main.py > features.txt &

wait

# Phase 2: Specialized analysis
echo "Given these metrics: $(cat metrics.txt), analyze trends and patterns" | python main.py > metrics_analysis.txt &
echo "Given this tech debt: $(cat tech_debt.txt), prioritize fixes by impact" | python main.py > debt_prioritization.txt &

wait

# Phase 3: Executive summary
cat > executive_summary_input.txt << EOF
You are an EXECUTIVE ANALYST. Create a high-level summary for stakeholders based on the following technical analyses:

=== METRICS ANALYSIS ===
$(cat metrics_analysis.txt | tail -20)

=== TECH DEBT PRIORITIZATION ===  
$(cat debt_prioritization.txt | tail -20)

=== DEPENDENCY RISKS ===
$(cat dependencies.txt | tail -10)

=== FEATURE OVERVIEW ===
$(cat features.txt | tail -10)

Create an executive summary focusing on:
1. Overall project health status
2. Top 3 priorities for attention
3. Resource allocation recommendations
4. Risk assessment summary
Keep it concise and business-focused.
EOF

cat executive_summary_input.txt | python main.py > executive_summary.txt

echo "📊 Full analysis report generated:"
echo "  - Raw data: metrics.txt, tech_debt.txt, dependencies.txt, features.txt"
echo "  - Analysis: metrics_analysis.txt, debt_prioritization.txt"  
echo "  - Executive summary: executive_summary.txt"
```

## Best Practices Checklist

### Before Launching Agents
- [ ] Clear task definitions
- [ ] Appropriate timeouts set
- [ ] Output directories created
- [ ] Environment variables configured
- [ ] Error handling planned
- [ ] Resource limits considered

### During Execution
- [ ] Monitor process counts
- [ ] Check for hung processes
- [ ] Validate output files
- [ ] Log agent status
- [ ] Handle partial failures

### After Completion
- [ ] Verify all outputs created
- [ ] Check result quality
- [ ] Clean up temporary files
- [ ] Aggregate results
- [ ] Document findings

These recipes and patterns provide practical, production-ready approaches for implementing sophisticated subagent workflows in AI Coder.
