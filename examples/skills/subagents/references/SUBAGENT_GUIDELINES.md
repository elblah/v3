# Subagent Guidelines

## Temp Directories

**Always** use `/tmp` or `./aicoder/tmp`, never project root:
```bash
TEMP_DIR="/tmp/subagent_$(date +%s%N)"
mkdir -p "$TEMP_DIR"
```

## Safe Script Template

```bash
#!/bin/bash
set -e
export YOLO_MODE=1
export MINI_SANDBOX=0

TEMP_DIR="/tmp/subagent_$(date +%s)"
mkdir -p "$TEMP_DIR"

# Cleanup on exit
trap 'rm -rf "$TEMP_DIR"' EXIT

# Run subagents...
```

## Output Validation

```bash
# Check all outputs exist and are non-empty
for f in /tmp/*.txt; do
    [ -s "$f" ] || echo "Warning: $f failed"
done
```