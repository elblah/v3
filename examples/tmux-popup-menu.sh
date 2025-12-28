#!/bin/bash
# AI Coder Popup Menu for TMUX

#set -euo pipefail

# Socket directory (uses TMPDIR or /tmp)
SOCKET_DIR="${TMPDIR:-/tmp}/aicoder-sockets"

# JSON parser (prefer gojq, fall back to jq, else use grep)
JSON_PARSER=""
if command -v gojq &>/dev/null; then
    JSON_PARSER="gojq"
elif command -v jq &>/dev/null; then
    JSON_PARSER="jq"
fi

pane_id=$(tmux display-message -p "#{pane_id}")
pane_numeric="${pane_id#%}"  # Remove % prefix if present

# Show error message and exit
show_error() {
    local msg="$1"
    tmux display-message -d 5000 "AI Coder: $msg"
    exit
}

if [[ -z "$pane_id" ]]; then
    show_error "No pane id..."
    exit 1
fi

# Find socket for current pane
find_socket() {
    # Try exact pane ID match first: aicoder-<pid>-<pane_id>-<random>.socket
    local socket=$(ls -tr1 "$SOCKET_DIR" \
         | grep -E "aicoder-[0-9]+-${pane_numeric}-.*"
    )

    [[ -z "$socket" ]] && return

    while read -r LINE; do
        SOCKFILE="${SOCKET_DIR}/${LINE}"
        if ! nc -w 1 -U -z "$SOCKFILE" &> /dev/null; then
            rm "$SOCKFILE"
            continue
        fi
        if [[ -z "$SSENT" ]]; then
            echo "$SOCKFILE"
            local SSENT=1
        fi
    done <<< "$socket"
}

# Send command to socket and return response
send_command() {
    local socket="$1"
    local cmd="$2"
    echo "$cmd" | nc -U "$socket" 2>/dev/null || echo ""
}

# Parse JSON field using gojq/jq or grep fallback
parse_json() {
    local json="$1"
    local field="$2"

    if [ -n "$JSON_PARSER" ]; then
        echo "$json" | $JSON_PARSER -r ".$field // empty" 2>/dev/null
    else
        # Fallback: grep for "field":value
        echo "$json" | grep -o "\"$field\":[^,}]*" | sed 's/.*://' | tr -d '"'
    fi
}

# Check if boolean field is true in JSON
parse_bool() {
    local json="$1"
    local field="$2"
    local value

    if [ -n "$JSON_PARSER" ]; then
        value=$(echo "$json" | $JSON_PARSER -r ".data.${field} // false" 2>/dev/null)
    else
        value=$(echo "$json" | grep -o "\"$field\":true" | wc -l)
    fi

    if [ "$value" = "true" ] || [ "$value" = "1" ]; then
        return 0
    else
        return 1
    fi
}

# ==================================================
# Menu Display
# ==================================================

# Show main popup menu
show_menu() {
    local socket="$1"

    # Get current status from socket
    local status_json=$(send_command "$socket" "status")

    # Parse status
    local yolo_enabled="OFF"
    local detail_enabled="OFF"
    local sandbox_enabled="OFF"
    local processing="Idle"

    if parse_bool "$status_json" "yolo_enabled"; then
        yolo_enabled="ON"
    fi
    if parse_bool "$status_json" "detail_enabled"; then
        detail_enabled="ON"
    fi
    if parse_bool "$status_json" "sandbox_enabled"; then
        sandbox_enabled="ON"
    fi
    if parse_bool "$status_json" "processing"; then
        processing="RUNNING"
    fi

    response_file="$TMP/aicoder_menu_resp_${pane_numeric}.tmp"
    tmux display-menu -T "#[align=centre]AICoder" \
        "Stop Processing (${processing})"        x "run-shell -b 'echo stop > ${response_file}'" \
        "Toggle YOLO (${yolo_enabled})"          y "run-shell -b 'echo yolo > ${response_file}'" \
        "Toggle Detail (${detail_enabled})"      d "run-shell -b 'echo detail > ${response_file}'" \
        "Toggle Sandbox-FS (${sandbox_enabled})" f "run-shell -b 'echo sandbox > ${response_file}'" \
        "Inject Message"    i  "run-shell -b 'echo inject > ${response_file}'" \
        "Save Session"      s  "run-shell -b 'echo save > ${response_file}'" \
        "Kill"              K  "run-shell -b 'echo kill > ${response_file}'" \
        "Quit"              Q  "run-shell -b 'echo quit > ${response_file}'"

    cat "$response_file"
    rm "$response_file"
}

# ==================================================
# Action Execution
# ==================================================

# Execute the selected action
execute_action() {
    local socket="$1"
    local choice="$2"

    # Get current status for toggles
    local status_json=$(send_command "$socket" "status")

    local cmd=""
    local display_msg=""
    local display_duration=3000

    case "$choice" in
        # Toggles
        "yolo"*)
            if parse_bool "$status_json" "yolo_enabled"; then
                cmd="yolo off"
                display_msg="YOLO Mode: OFF"
            else
                cmd="yolo on"
                display_msg="YOLO Mode: ON (auto-approve enabled)"
            fi
            ;;
        "detail"*)
            if parse_bool "$status_json" "detail_enabled"; then
                cmd="detail off"
                display_msg="Detail Mode: OFF"
            else
                cmd="detail on"
                display_msg="Detail Mode: ON"
            fi
            ;;
        "sandbox"*)
            if parse_bool "$status_json" "sandbox_enabled"; then
                cmd="sandbox off"
                display_msg="Sandbox: OFF (filesystem unrestricted)"
            else
                cmd="sandbox on"
                display_msg="Sandbox: ON (filesystem protected)"
            fi
            ;;

        # Actions
        "stop"*)
            cmd="stop"
            display_msg="Processing stopped"
            display_duration=2000
            ;;
        "inject"*)
            cmd="inject"
            display_msg="Injecting Message"
            display_duration=2000
            ;;
        "quit"*)
            cmd="quit"
            display_msg="Quit"
            display_duration=2000
            ;;
        "kill"*)
            cmd="kill"
            display_msg="Kill"
            display_duration=2000
            ;;

        "save"*)
            cmd="save"
            display_msg="Session saved"
            ;;
        "stats"*)
            # Get stats and format for display
            local stats_json=$(send_command "$socket" "stats")
            local api_req=$(parse_json "$stats_json" "api_requests" 2>/dev/null || echo "?")
            local msg_sent=$(parse_json "$stats_json" "messages_sent" 2>/dev/null || echo "?")
            display_msg="API: ${api_req} | Sent: ${msg_sent}"
            display_duration=5000
            ;;

        # Cancel
        "0"*|""|q|Q)
            exit 0
            ;;

        *)
            show_error "Invalid choice: $choice"
            exit 1
            ;;
    esac

    # Execute the command if set
    if [ -n "$cmd" ]; then
        local response=$(send_command "$socket" "$cmd")

        # Check for errors in response
        if echo "$response" | grep -q '"status":"error"'; then
            local error_msg=$(parse_json "$response" "message" 2>/dev/null || echo "Unknown error")
            tmux display-message -d 5000 "AI Coder: ERROR - $error_msg"
            exit 1
        fi

        # Display success message
        tmux display-message -d "$display_duration" "AI Coder: $display_msg"
    fi
}

# ==================================================
# Main Execution
# ==================================================

# Check if running inside tmux
if [ -z "${TMUX:-}" ]; then
    echo "This script must be run from within tmux" >&2
    echo "Usage: bind-key a run-shell -b '$(realpath "$0")'" >&2
    exit 1
fi

# Find socket for current pane
SOCKET=$(find_socket)

# Check if socket exists
if [ -z "$SOCKET" ]; then
    show_error "No AI Coder session found in pane."
    exit
fi

if [ ! -S "$SOCKET" ]; then
    show_error "Socket not found or invalid: $SOCKET"
    exit
fi

if [[ ! -n "$1" ]]; then
    # Get user choice from menu
    CHOICE=$(show_menu "$SOCKET")
else
    CHOICE=$1
fi

# Execute action if choice was made
if [ -n "$CHOICE" ]; then
    execute_action "$SOCKET" "$CHOICE"
fi
