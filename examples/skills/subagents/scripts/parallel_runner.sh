#!/bin/bash

# Universal Parallel Runner - Execute arbitrary tasks in parallel
# Usage: ./parallel_runner.sh "task1" "task2" "task3" ...

set -e

# Check for AICODER_CMD
if [ -z "$AICODER_CMD" ]; then
    echo "Error: AICODER_CMD environment variable is not set."
    echo "This should be provided by AI Coder wrapper script."
    exit 1
fi


# Export global settings for all subagents
export YOLO_MODE=1
export MINI_SANDBOX=0
export MAX_RETRIES=10

# Check if tasks provided
if [ $# -eq 0 ]; then
    echo "❌ Usage: $0 \"task1\" [\"task2\"] [\"task3\"] ..."
    echo "Example: $0 \"Analyze security\" \"Check performance\" \"Review code quality\""
    exit 1
fi

# Create temp directory for parallel execution
TEMP_DIR="/tmp/parallel_runner_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "🚀 Launching $# parallel agents..."

# Launch each task as a separate agent
TASK_COUNT=0
for task in "$@"; do
    TASK_COUNT=$((TASK_COUNT + 1))
    
    # Create unique output filename
    OUTPUT_FILE="$TEMP_DIR/task_${TASK_COUNT}.txt"
    
    # Launch agent in background
    echo "$task" | $AICODER_CMD > "$OUTPUT_FILE" &
    PID=$!
    
    echo "  📡 Agent $TASK_COUNT (PID: $PID): $task"
    
    # Store PID for waiting
    if [ $TASK_COUNT -eq 1 ]; then
        PIDS="$PID"
    else
        PIDS="$PIDS $PID"
    fi
done

echo ""
echo "⏳ Waiting for $TASK_COUNT agents to complete..."

# Wait for all agents to complete
wait $PIDS

echo "✅ All parallel agents completed!"
echo ""
echo "📊 Results Summary:"
echo "  - Execution directory: $TEMP_DIR"
echo "  - Number of agents: $TASK_COUNT"
echo ""

# Show summary of each result
for ((i=1; i<=TASK_COUNT; i++)); do
    OUTPUT_FILE="$TEMP_DIR/task_${i}.txt"
    
    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        echo "  ✅ Task $i: Success ($(wc -c < "$OUTPUT_FILE" | tr -d ' ') bytes)"
        
        # Show first few lines as preview
        if [ -s "$OUTPUT_FILE" ]; then
            echo "     Preview:"
            head -3 "$OUTPUT_FILE" | sed 's/^/       /'
        fi
    else
        echo "  ❌ Task $i: Failed or empty output"
    fi
    echo ""
done

# Create combined results file
cat > "$TEMP_DIR/combined_results.md" << EOF
# Parallel Execution Results

**Generated on:** $(date)  
**Execution Directory:** $TEMP_DIR  
**Number of Tasks:** $TASK_COUNT

## Individual Results
EOF

for ((i=1; i<=TASK_COUNT; i++)); do
    OUTPUT_FILE="$TEMP_DIR/task_${i}.txt"
    
    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        echo "" >> "$TEMP_DIR/combined_results.md"
        echo "### Task $i" >> "$TEMP_DIR/combined_results.md"
        echo "" >> "$TEMP_DIR/combined_results.md"
        echo '```' >> "$TEMP_DIR/combined_results.md"
        cat "$OUTPUT_FILE" >> "$TEMP_DIR/combined_results.md"
        echo '```' >> "$TEMP_DIR/combined_results.md"
    else
        echo "" >> "$TEMP_DIR/combined_results.md"
        echo "### Task $i - FAILED" >> "$TEMP_DIR/combined_results.md"
        echo "*No output generated or task failed*" >> "$TEMP_DIR/combined_results.md"
    fi
done

echo "" >> "$TEMP_DIR/combined_results.md"
echo "---" >> "$TEMP_DIR/combined_results.md"
echo "*Parallel execution completed using subagent system*" >> "$TEMP_DIR/combined_results.md"

echo "📋 Combined results: $TEMP_DIR/combined_results.md"

# Optional: Auto-cleanup after showing results
AUTO_CLEANUP=${AUTO_CLEANUP:-0}
if [ "$AUTO_CLEANUP" = "1" ]; then
    echo ""
    echo "🗂️ Auto-cleanup enabled. Cleaning temp directory..."
    rm -rf "$TEMP_DIR"
else
    echo ""
    echo "💡 Tip: Set AUTO_CLEANUP=1 to automatically clean up temp files"
    echo "   Example: AUTO_CLEANUP=1 $0 \"task1\" \"task2\""
fi

# Return temp directory for caller
echo "$TEMP_DIR"