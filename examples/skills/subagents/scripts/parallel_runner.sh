#!/bin/bash
set -e
export YOLO_MODE=1
export MINI_SANDBOX=0

if [ -z "$AICODER_CMD" ]; then
  echo "Error: AICODER_CMD not set (should be provided by aicoder wrapper)"
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "Usage: $0 \"task1\" \"task2\" ..."
  exit 1
fi

TEMP_DIR="/tmp/subagent_parallel_$(date +%s)"
mkdir -p "$TEMP_DIR"

for i in $(seq 1 $#); do
  eval "task=\$$i"
  echo "$task" | $AICODER_CMD > "$TEMP_DIR/out_$i.txt" &
done

wait

for i in $(seq 1 $#); do
  cat "$TEMP_DIR/out_$i.txt"
done
