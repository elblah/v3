#!/bin/bash

# Comprehensive Analysis - Multi-phase parallel analysis with synthesis
# Phase 1: Data collection, Phase 2: Analysis, Phase 3: Synthesis

set -e

# Export global settings for all subagents
export YOLO_MODE=1
export MINI_SANDBOX=0
export MAX_RETRIES=10

# Create temp directory for analysis workflow
TEMP_DIR="/tmp/comprehensive_analysis_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "🔍 Starting comprehensive analysis workflow..."

# Phase 1: Data Collection Agents
echo "📊 Phase 1: Data collection..."

echo "Extract all APIs and endpoints from codebase" | python main.py > "$TEMP_DIR/apis.txt" &
PID1=$!

echo "List all database queries and database interactions" | python main.py > "$TEMP_DIR/queries.txt" &
PID2=$!

echo "Identify all configuration files and settings" | python main.py > "$TEMP_DIR/config.txt" &
PID3=$!

echo "Catalog all external dependencies and libraries" | python main.py > "$TEMP_DIR/dependencies.txt" &
PID4=$!

wait $PID1 $PID2 $PID3 $PID4

echo "✅ Phase 1 completed - Data collection finished"

# Phase 2: Analysis Agents  
echo "🔬 Phase 2: Specialized analysis..."

# Security Analysis of collected data
AICODER_SYSTEM_PROMPT="You are a SECURITY ANALYST. Analyze the provided data for security vulnerabilities, authentication issues, input validation problems, and potential attack vectors. Focus on actionable security findings." \
echo "Analyze these APIs, queries, config files, and dependencies for security issues: $(cat "$TEMP_DIR/apis.txt" "$TEMP_DIR/queries.txt" "$TEMP_DIR/config.txt" "$TEMP_DIR/dependencies.txt")" | python main.py > "$TEMP_DIR/security_analysis.txt" &
PID5=$!

# Performance Analysis of collected data
AICODER_SYSTEM_PROMPT="You are a PERFORMANCE ANALYST. Analyze the provided data for performance bottlenecks, efficiency issues, resource usage problems, and scalability concerns. Identify specific optimization opportunities." \
echo "Analyze these APIs, queries, config files, and dependencies for performance issues: $(cat "$TEMP_DIR/apis.txt" "$TEMP_DIR/queries.txt" "$TEMP_DIR/config.txt" "$TEMP_DIR/dependencies.txt")" | python main.py > "$TEMP_DIR/performance_analysis.txt" &
PID6=$!

# Architecture Analysis of collected data
AICODER_SYSTEM_PROMPT="You are an ARCHITECTURE ANALYST. Analyze the provided data for design patterns, component relationships, structural issues, and architectural improvements. Focus on system design insights." \
echo "Analyze these APIs, queries, config files, and dependencies for architectural patterns and improvements: $(cat "$TEMP_DIR/apis.txt" "$TEMP_DIR/queries.txt" "$TEMP_DIR/config.txt" "$TEMP_DIR/dependencies.txt")" | python main.py > "$TEMP_DIR/architecture_analysis.txt" &
PID7=$!

# Risk Analysis of collected data
AICODER_SYSTEM_PROMPT="You are a RISK ANALYST. Analyze the provided data for potential risks, technical debt, maintenance challenges, and business impact. Focus on prioritized risk assessment." \
echo "Analyze these APIs, queries, config files, and dependencies for risks and technical debt: $(cat "$TEMP_DIR/apis.txt" "$TEMP_DIR/queries.txt" "$TEMP_DIR/config.txt" "$TEMP_DIR/dependencies.txt")" | python main.py > "$TEMP_DIR/risk_analysis.txt" &
PID8=$!

wait $PID5 $PID6 $PID7 $PID8

echo "✅ Phase 2 completed - Analysis finished"

# Phase 3: Synthesis Agent
echo "📋 Phase 3: Comprehensive synthesis..."

AICODER_SYSTEM_PROMPT="You are a TECHNICAL SYNTHESIS EXPERT. Create a comprehensive technical report that synthesizes security, performance, architecture, and risk analyses. Provide prioritized recommendations and executive summary. Make it actionable for technical leaders." \
echo "Create comprehensive technical report synthesizing these analyses:

=== SECURITY ANALYSIS ===
$(cat "$TEMP_DIR/security_analysis.txt")

=== PERFORMANCE ANALYSIS ===
$(cat "$TEMP_DIR/performance_analysis.txt")

=== ARCHITECTURE ANALYSIS ===
$(cat "$TEMP_DIR/architecture_analysis.txt")

=== RISK ANALYSIS ===
$(cat "$TEMP_DIR/risk_analysis.txt")

Create an executive summary, prioritize findings by severity, and provide actionable recommendations. Focus on business impact and technical next steps." | python main.py > "$TEMP_DIR/final_synthesis.txt" &
PID9=$!

wait $PID9

echo "✅ Phase 3 completed - Synthesis finished"

# Create analysis summary
cat > "$TEMP_DIR/analysis_summary.md" << EOF
# Comprehensive Analysis Report

**Generated on:** $(date)  
**Project:** $(pwd)  
**Analysis Directory:** $TEMP_DIR

## 📊 Phase 1: Data Collection
- **APIs & Endpoints:** $(wc -l < "$TEMP_DIR/apis.txt" | tr -d ' ') items
- **Database Queries:** $(wc -l < "$TEMP_DIR/queries.txt" | tr -d ' ') items  
- **Configuration Files:** $(wc -l < "$TEMP_DIR/config.txt" | tr -d ' ') items
- **Dependencies:** $(wc -l < "$TEMP_DIR/dependencies.txt" | tr -d ' ') items

## 🔬 Phase 2: Specialized Analysis
- **Security Analysis:** Available at $TEMP_DIR/security_analysis.txt
- **Performance Analysis:** Available at $TEMP_DIR/performance_analysis.txt
- **Architecture Analysis:** Available at $TEMP_DIR/architecture_analysis.txt
- **Risk Analysis:** Available at $TEMP_DIR/risk_analysis.txt

## 📋 Phase 3: Final Synthesis
**Comprehensive Report:** $TEMP_DIR/final_synthesis.txt

## 🎯 Key Findings Summary
$(tail -10 "$TEMP_DIR/final_synthesis.txt")

---

*Analysis conducted using subagent parallel processing workflow*
EOF

echo "📋 Analysis summary: $TEMP_DIR/analysis_summary.md"
echo ""
echo "✅ Comprehensive analysis completed!"
echo ""
echo "📊 Results available at:"
echo "  - Raw data: apis.txt, queries.txt, config.txt, dependencies.txt"
echo "  - Analysis: security_analysis.txt, performance_analysis.txt, architecture_analysis.txt, risk_analysis.txt"
echo "  - Final synthesis: final_synthesis.txt"
echo "  - Summary report: analysis_summary.md"
echo ""
echo "🗂️ All files located in: $TEMP_DIR"

# Cleanup function for optional use
cleanup_temp() {
    echo "Cleaning up temporary files in $TEMP_DIR..."
    rm -rf "$TEMP_DIR"
    echo "✅ Cleanup completed"
}

# Return temp directory and cleanup function
echo "$TEMP_DIR"
echo "To cleanup when done: cleanup_temp"