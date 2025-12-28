#!/bin/bash
# TMUX Integration Example for AI Coder

# Add these bindings to ~/.tmux.conf or use directly

# Function to find socket for current pane
aicoder_socket() {
    local pid=$(pgrep -f "python.*aicoder" | head -1)
    if [ -z "$pid" ]; then
        echo ""
        return
    fi
    echo "/tmp/aicoder-${pid}-${TMUX_PANE}.socket"
}

# Function to send command to socket
aicoder_cmd() {
    local socket=$(aicoder_socket)
    if [ -z "$socket" ] || [ ! -S "$socket" ]; then
        tmux display-message "AI Coder not running"
        return 1
    fi
    echo "$1" | nc -U "$socket" 2>/dev/null
}

# Example key bindings - add to ~/.tmux.conf:

# ============================================
# Basic Controls
# ============================================

# Check if AI is busy (Ctrl+A then =)
bind-key = run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        status=$(echo "is_processing" | nc -U "$socket" 2>/dev/null)
        tmux display-message "AI Status: $status"
    else
        tmux display-message "AI Coder not found"
    fi
'

# Stop current processing (Ctrl+A then Space)
bind-key Space run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        echo "stop" | nc -U "$socket" 2>/dev/null
        tmux display-message "Stopped AI processing"
    fi
'

# Save session (Ctrl+A then s)
bind-key s run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        resp=$(echo "save ~/.aicoder/tmux-save.json" | nc -U "$socket" 2>/dev/null)
        tmux display-message "$resp"
    fi
'

# ============================================
# Mode Toggles
# ============================================

# Toggle YOLO (Ctrl+A then Y)
bind-key Y run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        current=$(echo "yolo status" | nc -U "$socket" 2>/dev/null)
        if echo "$current" | grep -q "true"; then
            echo "yolo off" | nc -U "$socket" 2>/dev/null
            tmux display-message "YOLO: OFF"
        else
            echo "yolo on" | nc -U "$socket" 2>/dev/null
            tmux display-message "YOLO: ON"
        fi
    fi
'

# Toggle Detail (Ctrl+A then D)
bind-key D run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        current=$(echo "detail status" | nc -U "$socket" 2>/dev/null)
        if echo "$current" | grep -q "true"; then
            echo "detail off" | nc -U "$socket" 2>/dev/null
            tmux display-message "Detail: OFF"
        else
            echo "detail on" | nc -U "$socket" 2>/dev/null
            tmux display-message "Detail: ON"
        fi
    fi
'

# ============================================
# Information Display
# ============================================

# Show full status (Ctrl+A then i)
bind-key i run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        echo "status" | nc -U "$socket" 2>/dev/null | tmux display-message
    fi
'

# Show statistics (Ctrl+A then I)
bind-key I run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        echo "stats" | nc -U "$socket" 2>/dev/null | tmux display-message
    fi
'

# Show message count (Ctrl+A then m)
bind-key m run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        echo "messages count" | nc -U "$socket" 2>/dev/null | tmux display-message
    fi
'

# ============================================
# Quick Actions
# ============================================

# Retry last request (Ctrl+A then r)
bind-key r run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        echo "retry" | nc -U "$socket" 2>/dev/null
        tmux display-message "Retrying..."
    fi
'

# Compact memory (Ctrl+A then c)
bind-key c run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        resp=$(echo "compact 50" | nc -U "$socket" 2>/dev/null)
        tmux display-message "$resp"
    fi
'

# Reset conversation (Ctrl+A then R)
bind-key R run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n "$socket" ]; then
        read -p "Reset conversation? [y/N] " ans
        if [ "$ans" = "y" ]; then
            echo "reset" | nc -U "$socket" 2>/dev/null
            tmux display-message "Conversation reset"
        fi
    fi
'

# ============================================
# Interactive Menu
# ============================================

# Show command menu (Ctrl+A then ;)
bind-key \; run-shell -b '
    socket=$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -z "$socket" ]; then
        tmux display-message "AI Coder not found"
        exit
    fi

    MENU="stop:stop\nsave:save ~/backup.json\nstatus:status\nstats:stats\nmessages:messages count\nyolo-on:yolo on\nyolo-off:yolo off\ndetail-on:detail on\ndetail-off:detail off\nretry:retry\ncompact:compact\nreset:reset\nhelp:help\n"

    CHOICE=$(echo -e "$MENU" | fzf --prompt="AI Coder: " --height=40% --reverse)
    CMD=$(echo "$CHOICE" | cut -d: -f2)

    if [ -n "$CMD" ]; then
        RESP=$(echo "$CMD" | nc -U "$socket" 2>/dev/null)
        tmux display-message "$RESP"
    fi
'

# ============================================
# Custom command input
# ============================================

# Type command to send to AI Coder (Ctrl+A then :)
bind-key : command-prompt -p "AI Coder command: " "
    socket=\$(ls -t $TMPDIR/aicoder-*.socket 2>/dev/null | head -1)
    if [ -n \"\$socket\" ]; then
        echo \"%1\" | nc -U \"\$socket\" 2>/dev/null | tmux display-message
    fi
"

echo "TMUX integration examples configured!"
echo ""
echo "To use these key bindings, either:"
echo "1. Copy the bindings to ~/.tmux.conf"
echo "2. Run this script to test them in the current session"
