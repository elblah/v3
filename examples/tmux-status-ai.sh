#!/bin/bash

# status codes: 0 idle/clear 1 prompt 2 processing 3 approval 4 error/retrying

declare -A aicoders_window_status
declare -A tmux_pane_window_id
declare -A windows_names
declare -A aicoder_panes

# env scan starts immediately in parallel; results drained after the
# list-panes pass below (overlaps the tmux round trip).
exec 9< <(grep -aozH 'AICODER_TMUX_PANE=[^[:cntrl:]]*' /proc/[0-9]*/environ 2>/dev/null)

# single pass: window_id, pane_id, window_name
while read -r window_id pane_id window_title; do
    tmux_pane_window_id[$pane_id]="$window_id"
    aicoders_window_status[$window_id]=0
    windows_names[$window_id]="$window_title"
done < <(tmux list-panes -a -F '#{window_id} #{pane_id} #{window_name}')

# discover aicoder panes via AICODER_TMUX_PANE, set by the launcher in the
# agent env (plain TMUX_PANE is inherited by every pane shell, so it cannot
# discriminate). the value is the pane id; subprocesses inherit the var,
# the assoc array dedups.
while IFS= read -r -d '' hit <&9; do
    pane=${hit##*=}
    [[ -n $pane ]] && aicoder_panes[$pane]=1
done
exec 9<&-

# capture + classify discovered aicoder panes only
for pane_id in "${!aicoder_panes[@]}"; do
    [[ -z "${tmux_pane_window_id[$pane_id]:-}" ]] && continue
    wid=${tmux_pane_window_id[$pane_id]}
    # command substitution already strips trailing newlines, so this is the
    # last non-empty line, no sed/awk needed
    last_line=$(tmux capture-pane -p -t "$pane_id" 2>/dev/null)
    last_line=${last_line##*$'\n'}
    aicoders_window_status[$wid]=2 # processing (default while aicoder is alive)
    if [[ "$last_line" =~ ^\> ]]; then
        aicoders_window_status[$wid]=1
    elif [[ "$last_line" =~ Choose|Approve ]]; then
        aicoders_window_status[$wid]=3
    elif [[ "$last_line" =~ ^Retrying ]]; then
        aicoders_window_status[$wid]=4
    fi
done

for window_id in "${!aicoders_window_status[@]}"; do
    window_status=${aicoders_window_status[$window_id]}
    window_name="${windows_names[$window_id]}"
    window_name_clean="${window_name//[🔥🔁⛔]/}"
    if [[ "$window_status" == 0 ]]; then
        if [[ "$window_name" =~ [🔁🔥⛔] ]]; then
            tmux rename-window -t $window_id "$window_name_clean"
        fi
    elif [[ "$window_status" == 1 ]]; then
        if [[ "$window_name" =~ [🔁🔥⛔] ]]; then
            tmux rename-window -t $window_id "$window_name_clean"
            PROMPT_VISIBLE=1
        fi
    elif [[ "$window_status" == 2 ]]; then
        if [[ ! "$window_name" =~ 🔁 ]]; then
            tmux rename-window -t $window_id "$window_name_clean🔁"
        fi
    elif [[ "$window_status" == 4 ]]; then
        if [[ ! "$window_name" =~ ⛔ ]]; then
            tmux rename-window -t $window_id "$window_name_clean⛔"
        fi
    elif [[ "$window_status" == 3 ]]; then
        if [[ ! "$window_name" =~ 🔥 ]]; then
            tmux rename-window -t $window_id "$window_name_clean🔥"
            APPROVAL_PROMPT_VISIBLE=1
        fi
    fi
done

if [[ -v APPROVAL_PROMPT_VISIBLE ]] && [[ -e ~/.notify-prompt-all ]]; then
    PULSE_SINK="combined" timeout -k 1 5s espeak "approval available" &
elif [[ -v PROMPT_VISIBLE ]] && [[ -e ~/.notify-prompt-all ]]; then
    PULSE_SINK="combined" timeout -k 1 5s espeak "prompt available" &
fi
