#!/bin/bash

tmux_panes=$(tmux list-panes -a -F "#{session_name}:#{window_index}.#{pane_index} #{pane_pid} #{pane_current_command} #{window_name}")

while read -r pane_id pane_pid pane_cmd window_name; do
    if [[ "$pane_cmd" != "python" && "$pane_cmd" != "bun" ]]; then
        if [[ "$window_name" =~ [🔁🔥] ]]; then
            window_name_clean="${window_name//[🔥🔁]/}"
            tmux rename-window -t $pane_id "$window_name_clean"
        fi
        continue
    fi
    last_line=$(tmux capture-pane -pt $pane_id | sed -e :a -e '/^\n*$/{$d;N;ba}' | tail -n 1)
    window_name_clean="${window_name//[🔥🔁]/}"
    #echo "$pane_id $window_name"
    if [[ "$last_line" =~ ^\> ]]; then
        #echo "Prompt: $last_line"
        if [[ "$window_name" =~ [🔁🔥] ]]; then
            tmux rename-window -t $pane_id "$window_name_clean"
            PROMPT_VISIBLE=1
        fi
    elif [[ "$last_line" =~ Choose|Approve ]]; then
        #echo "Approval: $last_line"
        if [[ ! "$window_name" =~ 🔥 ]]; then
            tmux rename-window -t $pane_id "$window_name_clean🔥"
            APPROVAL_PROMPT_VISIBLE=1
        fi
    else
        #echo "Processing: $last_line - $window_name"
        if [[ ! "$window_name" =~ 🔁 ]]; then
            tmux rename-window -t $pane_id "$window_name_clean🔁"
        fi
    fi
done <<< "$tmux_panes"

if [[ -v APPROVAL_PROMPT_VISIBLE ]] && [[ -e ~/.notify-prompt-all ]]; then
    PULSE_SINK="combined" timeout -k 1 3s espeak "approval available" &
elif [[ -v PROMPT_VISIBLE ]] && [[ -e ~/.notify-prompt-all ]]; then
    PULSE_SINK="combined" timeout -k 1 3s espeak "prompt available" &
fi
