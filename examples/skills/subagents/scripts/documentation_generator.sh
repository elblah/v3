#!/bin/bash
set -e
export YOLO_MODE=1
export MINI_SANDBOX=0

if [ -z "$AICODER_CMD" ]; then
  echo "Error: AICODER_CMD not set (should be provided by aicoder wrapper)"
  exit 1
fi

TEMP_DIR="/tmp/subagent_docs_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "Document all APIs" | TOOLS_ALLOW="read_file,grep,list_directory" $AICODER_CMD > "$TEMP_DIR/api.txt" &
echo "Document architecture" | TOOLS_ALLOW="read_file,grep" $AICODER_CMD > "$TEMP_DIR/arch.txt" &
echo "Document setup" | TOOLS_ALLOW="read_file,grep" $AICODER_CMD > "$TEMP_DIR/setup.txt" &

wait

cat "$TEMP_DIR/api.txt"
cat "$TEMP_DIR/arch.txt"
cat "$TEMP_DIR/setup.txt"
