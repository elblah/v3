#!/bin/bash
# Quick start for AI Coder socket API

# Find the socket
SOCKET=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)

if [ -z "$SOCKET" ]; then
    echo "❌ No AI Coder socket found."
    echo "   Make sure AI Coder is running!"
    exit 1
fi

echo "🔌 Found socket: $SOCKET"
echo ""

# Quick health check
echo "📊 Quick Status:"
echo "is_processing" | nc -U "$SOCKET" 2>/dev/null
echo ""

# Toggle YOLO
echo "🚀 Toggle YOLO Mode:"
current=$(echo "yolo status" | nc -U "$SOCKET" 2>/dev/null)
if echo "$current" | grep -q "true"; then
    echo "yolo off" | nc -U "$SOCKET" 2>/dev/null
    echo "   YOLO: OFF"
else
    echo "yolo on" | nc -U "$SOCKET" 2>/dev/null
    echo "   YOLO: ON"
fi
echo ""

# Get stats
echo "📈 Statistics:"
echo "stats" | nc -U "$SOCKET" 2>/dev/null
echo ""

echo "✅ Done! See docs/SOCKET_API.md for more commands."
