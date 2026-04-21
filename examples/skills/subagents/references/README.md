# Subagents References

## Documents
- `SUBAGENT_GUIDELINES.md` - Temp directories, safe scripts, validation
- `TIMEOUT_GUIDELINES.md` - Timeout recommendations by agent count

## Quick Start

```bash
export YOLO_MODE=1
export MINI_SANDBOX=0

# Launch parallel agents
echo "Task 1" | $AICODER_CMD > /tmp/out1.txt &
echo "Task 2" | $AICODER_CMD > /tmp/out2.txt &
wait
```
