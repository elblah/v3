#!/bin/bash
set -e
export YOLO_MODE=1
export MINI_SANDBOX=0

if [ -z "$AICODER_CMD" ]; then
  echo "Error: AICODER_CMD not set (should be provided by aicoder wrapper)"
  exit 1
fi

TEMP_DIR="/tmp/subagent_review_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "Security" | AICODER_SYSTEM_PROMPT="You are a security auditor. List specific issues." $AICODER_CMD > "$TEMP_DIR/security.txt" &
echo "Performance" | AICODER_SYSTEM_PROMPT="You are a performance analyst. List specific bottlenecks." $AICODER_CMD > "$TEMP_DIR/performance.txt" &
echo "Quality" | AICODER_SYSTEM_PROMPT="You are a code quality reviewer. List specific concerns." $AICODER_CMD > "$TEMP_DIR/quality.txt" &

wait

cat "$TEMP_DIR/security.txt"
cat "$TEMP_DIR/performance.txt"
cat "$TEMP_DIR/quality.txt"
