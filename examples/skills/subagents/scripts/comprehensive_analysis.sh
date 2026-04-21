#!/bin/bash
set -e
export YOLO_MODE=1
export MINI_SANDBOX=0

if [ -z "$AICODER_CMD" ]; then
  echo "Error: AICODER_CMD not set (should be provided by aicoder wrapper)"
  exit 1
fi

TEMP_DIR="/tmp/subagent_comprehensive_$(date +%s)"
mkdir -p "$TEMP_DIR"

# Phase 1
echo "List Python files" | $AICODER_CMD > "$TEMP_DIR/files.txt" &
echo "Extract config" | $AICODER_CMD > "$TEMP_DIR/config.txt" &
wait

# Phase 2
echo "Analyze files: $(cat "$TEMP_DIR/files.txt")" | $AICODER_CMD > "$TEMP_DIR/analyze.txt" &
wait

# Phase 3
echo "Create report from: $(cat "$TEMP_DIR/analyze.txt")" | $AICODER_CMD > "$TEMP_DIR/report.txt"

cat "$TEMP_DIR/report.txt"
