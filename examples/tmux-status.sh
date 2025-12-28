#!/bin/bash
# AI Coder Status Bar Indicator
# Shows current processing status in tmux status line
#
# Usage in ~/.tmux.conf:
#   set -g status-right '#{?pane_synchronized,,} %H:%M %Y-%m-%d | #(/home/blah/poc/aicoder/v3/examples/tmux-status.sh)'

set -euo pipefail

# Socket directory
SOCKET_DIR="${TMPDIR:-/tmp}"

# Find socket for current pane
SOCKET="${SOCKET_DIR}/aicoder-${TMUX_PANE#%}-$(pgrep -f "python.*aicoder" | head -1).socket"

# Fallback to most recent socket
if [ ! -S "$SOCKET" ]; then
    SOCKET=$(ls -t "$SOCKET_DIR"/aicoder-*.socket 2>/dev/null | head -1)
fi

# Check if socket exists
if [ ! -S "$SOCKET" ]; then
    exit 0
fi

# Get status
STATUS=$(echo "status" | nc -U "$SOCKET" 2>/dev/null || "")

# Check if processing
if echo "$STATUS" | grep -q '"processing":true'; then
    echo "#[fg=red,bold]AI:Running#[fg=default]"
else
    echo "#[fg=green]AI:Ready#[fg=default]"
fi
