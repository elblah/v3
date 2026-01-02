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

### Parallel Execution
- Launch multiple processes in background using `&`
- Capture process IDs for coordination
- Use `wait` for synchronization
- Handle failures and partial results gracefully

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
AICODER_SYSTEM_PROMPT="You are a SECURITY REVIEWER. Focus only on security vulnerabilities, authentication issues, input validation, and potential attack vectors." \
echo "Review the codebase for security issues" | python main.py > security_review.txt &

# Performance Reviewer  
AICODER_SYSTEM_PROMPT="You are a PERFORMANCE REVIEWER. Focus only on performance issues, efficiency, resource usage, and scalability concerns." \
echo "Review the codebase for performance issues" | python main.py > performance_review.txt &

# Code Quality Reviewer
AICODER_SYSTEM_PROMPT="You are a CODE QUALITY REVIEWER. Focus only on maintainability, design patterns, and best practices." \
echo "Review the codebase for code quality issues" | python main.py > quality_review.txt &

wait  # Wait for all reviews to complete
```

### Pattern 2: Parallel Documentation Generation
Generate different documentation types simultaneously:

```bash
# API Documentation
echo "Extract and document all APIs" | python main.py > api_docs.txt &

# Architecture Documentation
echo "Document architecture patterns and design" | python main.py > arch_docs.txt &

# Setup Documentation  
echo "Document installation and configuration" | python main.py > setup_docs.txt &

wait  # Wait for all documentation to complete
```

### Pattern 3: Research and Synthesis
Multiple research angles with final synthesis:

```bash
# Phase 1: Parallel research
echo "Research technical aspects of X" | python main.py > technical_research.txt &
echo "Research business aspects of X" | python main.py > business_research.txt &
echo "Research user experience aspects of X" | python main.py > ux_research.txt &
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

cat synthesis_input.txt | python main.py > final_synthesis.txt
```

## Configuration Requirements

### Essential Environment Variables
Always set these for reliable subagent execution:

```bash
export YOLO_MODE=1        # Auto-approve all tool actions
export MINI_SANDBOX=0     # Full file access for agents
export MAX_RETRIES=10       # Handle API issues gracefully
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
echo "Extract all API endpoints" | python main.py > endpoints.txt &
echo "List all database queries" | python main.py > queries.txt &
wait

# Phase 2: Analysis of collected data
echo "Analyze these endpoints for security: $(cat endpoints.txt)" | python main.py > endpoint_security.txt &
echo "Analyze these queries for performance: $(cat queries.txt)" | python main.py > query_performance.txt &
wait

# Phase 3: Final synthesis
echo "Create security report from: endpoint_security.txt + query_performance.txt" | python main.py > final_security_report.txt
```

### Competitive Analysis
Multiple approaches to same problem for comparison:

```bash
# Different architectures for same task
AICODER_SYSTEM_PROMPT="You are an ENTERPRISE ARCHITECT. Focus on scalability, maintainability, and enterprise patterns." \
echo "Design authentication system" | python main.py > enterprise_design.txt &

AICODER_SYSTEM_PROMPT="You are a STARTUP ARCHITECT. Focus on speed, simplicity, and rapid development." \
echo "Design authentication system" | python main.py > startup_design.txt &

AICODER_SYSTEM_PROMPT="You are a SECURITY ARCHITECT. Focus on zero-trust, encryption, and defense in depth." \
echo "Design authentication system" | python main.py > security_design.txt &

wait

# Compare and recommend
echo "Compare these three authentication designs and recommend best approach: enterprise_design.txt + startup_design.txt + security_design.txt" | python main.py > design_comparison.txt
```

## Keywords

subagents, parallel agents, multi-agent, concurrent processing, parallel execution, simultaneous analysis, multi-perspective review, code review, security audit, performance analysis, documentation generation, research synthesis, competitive analysis, hierarchical workflow