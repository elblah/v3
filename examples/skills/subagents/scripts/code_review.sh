#!/bin/bash

# Code Review Subagents - Multi-perspective parallel code review
# Launches security, performance, and quality reviewers simultaneously

set -e

# Export global settings for all subagents
export YOLO_MODE=1
export MINI_SANDBOX=0
export MAX_RETRIES=10

# Create temp directory for review outputs
TEMP_DIR="/tmp/subagent_review_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "🔍 Launching multi-perspective code review..."

# Security Reviewer
AICODER_SYSTEM_PROMPT="You are a SECURITY REVIEWER. Focus exclusively on security vulnerabilities, authentication issues, input validation problems, and potential attack vectors. Provide specific, actionable findings with severity levels." \
echo "Review the codebase for security issues and vulnerabilities. Focus on authentication, input validation, file permissions, and potential attack vectors." | python main.py > "$TEMP_DIR/security_review.txt" &
PID1=$!

# Performance Reviewer  
AICODER_SYSTEM_PROMPT="You are a PERFORMANCE REVIEWER. Focus exclusively on performance bottlenecks, efficiency issues, resource usage problems, and scalability concerns. Identify specific optimization opportunities." \
echo "Review the codebase for performance issues. Look for inefficient algorithms, memory leaks, database query problems, and scalability limitations." | python main.py > "$TEMP_DIR/performance_review.txt" &
PID2=$!

# Code Quality Reviewer
AICODER_SYSTEM_PROMPT="You are a CODE QUALITY REVIEWER. Focus exclusively on maintainability, design patterns, code organization, and best practices violations. Highlight specific improvements needed." \
echo "Review the codebase for code quality issues. Examine structure, naming conventions, documentation, error handling, and adherence to best practices." | python main.py > "$TEMP_DIR/quality_review.txt" &
PID3=$!

# Testing Reviewer
AICODER_SYSTEM_PROMPT="You are a TESTING REVIEWER. Focus exclusively on test coverage, test quality, edge cases, and testing strategy. Identify gaps and improvements needed." \
echo "Review the codebase for testing issues. Analyze test coverage, test quality, missing edge cases, and overall testing strategy." | python main.py > "$TEMP_DIR/testing_review.txt" &
PID4=$!

echo "📡 Code reviewers launched (PIDs: $PID1, $PID2, $PID3, $PID4)"
echo "⏳ Waiting for all reviews to complete..."

# Wait for all reviewers to complete
wait $PID1 $PID2 $PID3 $PID4

echo "✅ Code review completed!"
echo ""
echo "📊 Review Results:"
echo "  - Security Review: $TEMP_DIR/security_review.txt"
echo "  - Performance Review: $TEMP_DIR/performance_review.txt"
echo "  - Code Quality Review: $TEMP_DIR/quality_review.txt"
echo "  - Testing Review: $TEMP_DIR/testing_review.txt"
echo ""

# Generate combined summary
cat > "$TEMP_DIR/combined_review.md" << EOF
# Comprehensive Code Review Report

## 🔒 Security Analysis
$(cat "$TEMP_DIR/security_review.txt")

## ⚡ Performance Analysis  
$(cat "$TEMP_DIR/performance_review.txt")

## 📊 Code Quality Analysis
$(cat "$TEMP_DIR/quality_review.txt")

## 🧪 Testing Analysis
$(cat "$TEMP_DIR/testing_review.txt")

## 📋 Summary & Recommendations
Generated on: $(date)
Review location: $TEMP_DIR
EOF

echo "📋 Combined report: $TEMP_DIR/combined_review.md"
echo ""
echo "🔍 Key findings:"
if grep -q "CRITICAL\|HIGH\|vulnerability\|security" "$TEMP_DIR/security_review.txt"; then
    echo "  ⚠️  Security issues found - see security review"
fi

if grep -q "performance\|bottleneck\|optimization\|scalability" "$TEMP_DIR/performance_review.txt"; then
    echo "  ⚡  Performance concerns identified - see performance review"
fi

if grep -q "quality\|maintainability\|improvement" "$TEMP_DIR/quality_review.txt"; then
    echo "  📊  Code quality improvements needed - see quality review"
fi

# Return temp directory path for caller
echo "$TEMP_DIR"