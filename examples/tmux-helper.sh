#!/bin/bash
# AI Coder TMUX Helper - Execute single commands
#
# Usage:
#   tmux-helper.sh <command>
#   tmux-helper.sh stop
#   tmux-helper.sh "yolo toggle"
#
# Example tmux binding:
#   bind-key s run-shell -b '/path/to/tmux-helper.sh stop'

set -euo pipefail

# ==================================================
# Configuration
# ==================================================

# Socket directory (uses TMPDIR or /tmp)
SOCKET_DIR="${TMPDIR:-/tmp}"

# JSON parser (prefer gojq, fall back to jq, else use grep)
JSON_PARSER=""
if command -v gojq &>/dev/null; then
    JSON_PARSER="gojq"
elif command -v jq &>/dev/null; then
    JSON_PARSER="jq"
fi

# ==================================================
# Helper Functions
# ==================================================

# Find socket for current pane
find_socket() {
    local pane_id="${TMUX_PANE:-0}"
    local pane_numeric="${pane_id#%}"  # Remove % prefix if present

    # Try exact pane ID match first
    local socket=$(ls -t "$SOCKET_DIR"/aicoder-*-"$pane_numeric"*.socket 2>/dev/null | head -1)

    # Fall back to most recent socket
    if [ -z "$socket" ]; then
        socket=$(ls -t "$SOCKET_DIR"/aicoder-*.socket 2>/dev/null | head -1)
    fi

    echo "$socket"
}

# Send command to socket
send_command() {
    local socket="$1"
    local cmd="$2"
    echo "$cmd" | nc -U "$socket" 2>/dev/null || echo ""
}

# Parse JSON field
parse_json() {
    local json="$1"
    local field="$2"

    if [ -n "$JSON_PARSER" ]; then
        echo "$json" | $JSON_PARSER -r ".$field // empty" 2>/dev/null
    else
        echo "$json" | grep -o "\"$field\":[^,}]*" | sed 's/.*://' | tr -d '"'
    fi
}

# ==================================================
# Main
# ==================================================

# Check for command argument
if [ $# -eq 0 ]; then
    echo "Usage: $0 <command>" >&2
    echo "Example: $0 stop" >&2
    echo "         $0 \"yolo toggle\"" >&2
    exit 1
fi

COMMAND="$1"

# Check if running inside tmux
if [ -z "${TMUX:-}" ]; then
    echo "This script must be run from within tmux" >&2
    echo "Usage: bind-key s run-shell -b '$(realpath "$0") stop'" >&2
    exit 1
fi

# Find socket for current pane
SOCKET=$(find_socket)

# Check if socket exists
if [ -z "$SOCKET" ] || [ ! -S "$SOCKET" ]; then
    tmux display-message -d 4000 "AI Coder: No session found in pane ${TMUX_PANE:-unknown}"
    exit 1
fi

# Execute command
RESPONSE=$(send_command "$SOCKET" "$COMMAND")

# Handle response
if [ -z "$RESPONSE" ]; then
    tmux display-message -d 3000 "AI Coder: No response"
    exit 1
fi

# Check for error in response
if echo "$RESPONSE" | grep -q '"status":"error"'; then
    ERROR_MSG=$(parse_json "$RESPONSE" "message" 2>/dev/null || echo "Unknown error")
    tmux display-message -d 5000 "AI Coder: ERROR - $ERROR_MSG"
    exit 1
fi

# Extract message for display
MSG=$(parse_json "$RESPONSE" "message" 2>/dev/null)

if [ -n "$MSG" ]; then
    # Display the message from response
    tmux display-message -d 3000 "AI Coder: $MSG"
else
    # For commands without explicit message, show success
    tmux display-message -d 3000 "AI Coder: Command executed"
fi
