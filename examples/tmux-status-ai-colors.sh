#!/bin/bash

# Color-only variant of tmux-status-ai.sh: window status styles instead of
# emojis. No rename-window calls — window names belong to aicoder wintitle.
#
# status codes: 0 idle/clear 1 prompt 2 processing 3 approval 4 error/retrying
# tab colors:
#   2 processing -> dark green bg, white fg
#   4 retrying   -> red bg, white fg
#   3 approval   -> orange bg, white fg
#   1 prompt     -> default (styles unset, your tmux config applies)
#   0 idle       -> default
# Multiple aicoder panes in one window: the most important state wins:
#   1 prompt > 3 approval > 4 retry > 2 processing > 0 idle
# Style writes happen on transitions only. Pane/window history lives in
# STATE_FILE so transitions and espeak notifications survive both one-shot
# per-tick invocations and a long-running loop.

STATE_FILE=/tmp/aicoder-status-ai-colors.state

declare -A prev_pane_state
declare -A prev_win_code    # wid -> style code applied on previous run (0 = default)
declare -A pane_window_id
declare -A pane_state
declare -A win_code         # wid -> aggregated state for windows holding aicoders
declare -A aicoder_panes

state_rank() { # higher rank = more important, wins the window
    case $1 in
        1) echo 4 ;;
        3) echo 3 ;;
        4) echo 2 ;;
        2) echo 1 ;;
        *) echo 0 ;;
    esac
}

apply_style() { # wid code
    local wid=$1 code=$2
    case $code in
        2) tmux set -w -t "$wid" window-status-style 'bg=#00cdcd,fg=#ffffff' ;; # Processing
        4) tmux set -w -t "$wid" window-status-style 'bg=#ff0000,fg=#ffff00' ;; # Retrying
        3) tmux set -w -t "$wid" window-status-style 'bg=#cd00cd,fg=#ffff00' ;; # Approval
        *) tmux set -w -u -t "$wid" window-status-style 2>/dev/null ;;
    esac
}

if [[ -r $STATE_FILE ]]; then
    while read -r kind key value; do
        case $kind in
            P) prev_pane_state[$key]=$value ;;
            W) prev_win_code[$key]=$value ;;
        esac
    done < "$STATE_FILE"
fi

# env scan starts immediately in parallel; results drained after the
# list-panes pass below (overlaps the tmux round trip).
exec 9< <(grep -aozH 'AICODER_TMUX_PANE=[^[:cntrl:]]*' /proc/[0-9]*/environ 2>/dev/null)

# single pass: window_id, pane_id
while read -r window_id pane_id _; do
    pane_window_id[$pane_id]="$window_id"
done < <(tmux list-panes -a -F '#{window_id} #{pane_id}')

# discover aicoder panes via AICODER_TMUX_PANE, set by the launcher in the
# agent env (plain TMUX_PANE is inherited by every pane shell, so it cannot
# discriminate). the value is the pane id; subprocesses inherit the var,
# the assoc array dedups.
while IFS= read -r -d '' hit <&9; do
    pane=${hit##*=}
    [[ -n $pane ]] && aicoder_panes[$pane]=1
done
exec 9<&-

for pane_id in "${!aicoder_panes[@]}"; do
    wid=${pane_window_id[$pane_id]:-}
    [[ -z $wid ]] && continue
    win_code[$wid]=0
    # command substitution already strips trailing newlines, so this is the
    # last non-empty line, no sed/awk needed
    last_line=$(tmux capture-pane -p -t "$pane_id" 2>/dev/null)
    last_line=${last_line##*$'\n'}
    state=2 # processing (default while aicoder is alive)
    if [[ "$last_line" =~ ^\> ]]; then
        state=1
    elif [[ "$last_line" =~ Choose|Approve ]]; then
        state=3
    elif [[ "$last_line" =~ ^Retrying ]]; then
        state=4
    fi
    pane_state[$pane_id]=$state
    if (( $(state_rank "$state") > $(state_rank "${win_code[$wid]}") )); then
        win_code[$wid]=$state
    fi
    # espeak fires on transitions only; no history on first run (no state file)
    prev=${prev_pane_state[$pane_id]:-}
    [[ -z $prev ]] && continue
    if (( state == 1 && prev >= 2 )); then
        notify_prompt=1
    elif (( state == 3 && prev != 3 )); then
        notify_approval=1
    fi
done

for wid in "${!win_code[@]}"; do
    code=${win_code[$wid]}
    old=${prev_win_code[$wid]:-0}
    if (( code != old )); then
        apply_style "$wid" "$code"
    fi
done

# aicoder exited but its window was left colored -> clear the stale style
for wid in "${!prev_win_code[@]}"; do
    if [[ -z ${win_code[$wid]:-} && ${prev_win_code[$wid]} != 0 ]]; then
        apply_style "$wid" 0
    fi
done

: > "$STATE_FILE"
for pane_id in "${!pane_state[@]}"; do
    printf 'P %s %s\n' "$pane_id" "${pane_state[$pane_id]}" >> "$STATE_FILE"
done
for wid in "${!win_code[@]}"; do
    (( win_code[$wid] == 0 )) && continue
    printf 'W %s %s\n' "$wid" "${win_code[$wid]}" >> "$STATE_FILE"
done

if [[ -v notify_approval ]] && [[ -e ~/.notify-prompt-all ]]; then
    PULSE_SINK="combined" timeout -k 1 5s espeak "approval available" &
elif [[ -v notify_prompt ]] && [[ -e ~/.notify-prompt-all ]]; then
    PULSE_SINK="combined" timeout -k 1 5s espeak "prompt available" &
fi
