#!/bin/bash
# Example script showing AI Coder socket API usage
# Great for tmux key bindings!

# Find the socket (most recent)
SOCKET=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)

if [ -z "$SOCKET" ]; then
    echo "No AI Coder socket found!"
    exit 1
fi

echo "Using socket: $SOCKET"

# Check if AI is processing
PROCESSING=$(echo "is_processing" | nc -U "$SOCKET" 2>/dev/null)
echo "Processing status: $PROCESSING"

# Get full status
echo ""
echo "=== Full Status ==="
echo "status" | nc -U "$SOCKET" 2>/dev/null

# Get statistics
echo ""
echo "=== Statistics ==="
echo "stats" | nc -U "$SOCKET" 2>/dev/null

# Get message count
echo ""
echo "=== Message Count ==="
echo "messages count" | nc -U "$SOCKET" 2>/dev/null

# Save session
echo ""
echo "=== Saving Session ==="
echo "save ~/aicoder-backup.json" | nc -U "$SOCKET" 2>/dev/null

# Toggle YOLO
echo ""
echo "=== Toggle YOLO ==="
echo "yolo on" | nc -U "$SOCKET" 2>/dev/null
echo "yolo status" | nc -U "$SOCKET" 2>/dev/null

# Inject a message
echo ""
echo "=== Injecting Message ==="
echo "inject list all files" | nc -U "$SOCKET" 2>/dev/null

# Inject multiline text using base64
echo ""
echo "=== Injecting Multiline Text ==="
MULTILINE="Write a function that:\n1. Takes a list\n2. Returns the sum\n3. Handles empty lists"
ENCODED=$(printf "$MULTILINE" | base64 -w0)
echo "inject-text $ENCODED" | nc -U "$SOCKET" 2>/dev/null

# Stop if processing
echo ""
echo "=== Stop Processing (if needed) ==="
echo "stop" | nc -U "$SOCKET" 2>/dev/null

echo ""
echo "Done!"
