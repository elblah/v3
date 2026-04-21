#!/bin/bash
# Basic 4-agent parallel launcher
set -e
export YOLO_MODE=1
export MINI_SANDBOX=0

if [ -z "$AICODER_CMD" ]; then
  echo "Error: AICODER_CMD not set (should be provided by aicoder wrapper)"
  exit 1
fi

TEMP_DIR="/tmp/subagent_basic_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "Launching 4 agents..."

echo "What is this codebase? Be brief." | $AICODER_CMD > "$TEMP_DIR/explorer.txt" &
echo "List top 5 features from README.md" | $AICODER_CMD > "$TEMP_DIR/features.txt" &
echo "Analyze main modules and their purpose" | $AICODER_CMD > "$TEMP_DIR/structure.txt" &
echo "Describe the plugin system" | $AICODER_CMD > "$TEMP_DIR/plugins.txt" &

wait

echo "Done. Results in $TEMP_DIR"
cat "$TEMP_DIR/explorer.txt"
