#!/bin/bash

# Basic Subagent Launcher - Runs 4 specialized agents in parallel
# Each agent analyzes different aspects of the codebase

set -e

# Export global settings for all subagents
export YOLO_MODE=1
export MINI_SANDBOX=0
export MAX_RETRIES=10

# Create temp directory for outputs
TEMP_DIR="/tmp/subagent_basic_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "🚀 Launching 4 subagents for basic analysis..."

# Subagent 1: File Explorer (using default system prompt)
echo "Analyze this codebase and tell me what it is in 2-3 sentences." | python main.py > "$TEMP_DIR/file_explorer.txt" &
PID1=$!

# Subagent 2: Documentation Analyzer (using default system prompt)  
echo "Read the README.md file and list the top 5 key features in bullet points." | python main.py > "$TEMP_DIR/doc_analysis.txt" &
PID2=$!

# Subagent 3: Code Structure Analyzer (custom prompt for demo)
AICODER_SYSTEM_PROMPT="You are a CODE STRUCTURE ANALYZER. Your only job is to analyze Python code structure and identify architectural patterns. Be brief and technical." \
echo "Analyze the main.py file and the aicoder/core/ directory structure. What are the main components?" | python main.py > "$TEMP_DIR/code_structure.txt" &
PID3=$!

# Subagent 4: Plugin System Analyzer (using default system prompt)
echo "Analyze the plugins/ directory and the plugin system. How do plugins work in this codebase?" | python main.py > "$TEMP_DIR/plugin_analysis.txt" &
PID4=$!

echo "📡 All subagents launched (PIDs: $PID1, $PID2, $PID3, $PID4)"
echo "⏳ Waiting for all subagents to complete..."

# Wait for all subagents to complete
wait $PID1 $PID2 $PID3 $PID4

echo "✅ All subagents completed!"
echo ""
echo "📊 Results:"
echo "  - File Explorer: $TEMP_DIR/file_explorer.txt"
echo "  - Documentation: $TEMP_DIR/doc_analysis.txt" 
echo "  - Code Structure: $TEMP_DIR/code_structure.txt"
echo "  - Plugin Analysis: $TEMP_DIR/plugin_analysis.txt"
echo ""
echo "🔍 Sample results:"
echo "--- File Explorer ---"
head -5 "$TEMP_DIR/file_explorer.txt"
echo ""
echo "--- Documentation ---"
head -5 "$TEMP_DIR/doc_analysis.txt"

# Return temp directory path for caller
echo "$TEMP_DIR"