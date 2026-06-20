#!/bin/bash

plugins=$(find plugins -name "*.py" | grep -v test_)

if [[ "$@" =~ --help ]]; then
    echo "--update  - update installed plugins"
    echo "--default - install all plugins without selection"
    exit
fi

if [[ "$@" =~ --update ]]; then
    tmp_sels=""
    while read -r plugin; do
        filename="${plugin##*/}"
        plug_inst_path="$HOME/.config/aicoder-v3/plugins/${filename}"
        [[ ! -e "$plug_inst_path" ]] && continue
        if ! cmp "$plugin" "$plug_inst_path" &> /dev/null; then
            tmp_sels+="${plugin}\n"
        fi
    done <<< "$plugins"
    sels="$(printf "$tmp_sels")"
elif [[ "$@" =~ --default ]]; then
    # Hardcoded list of plugins currently installed on this computer
    DEFAULT_PLUGINS=(
        a11y.py alibaba_transform.py anthropic_prompt_cache.py audio.py
        auto_next_prompt.py auto_pruner.py autoexec.py bg_jobs.py clipboard.py
        command_completer.py compact_strategy.py copy.py empty_retry.py
        git_aware.py goal.py httpx_http.py initial_prompt.py loop_detector.py
        luna_theme.py mdfmt.py model_switch.py notify_prompt.py orjson_fast.py
        pinned.py presets.py prompt_reloader.py ralph.py ruff.py session-autosaver.py
        shell.py shutdown_recovery.py skills.py snippets.py stats_logger.py timeit.py
        tools_manager.py tts_reader.py vision.py web_search.py
    )
    sels=""
    for p in "${DEFAULT_PLUGINS[@]}"; do
        [[ -f "plugins/$p" ]] && sels+="plugins/$p\n"
    done
    sels="$(printf "$sels")"
else
    echo "Select plugins to install (use TAB to multi-select, ENTER to confirm):"
    sels=$(echo "$plugins" | fzf -m -e)
fi

[ -z "$sels" ] && exit 1

mkdir -p ~/.config/aicoder-v3/plugins

# Get the aicoder source directory
AICODER_DIR=$(cd "$(dirname "$0")" && pwd)

while read -r LINE; do
    # Compile TypeScript to JavaScript during installation
    cp -v "$LINE" ~/.config/aicoder-v3/plugins/
done <<< "$sels"

if [ -n "$sels" ]; then
    echo ""
    echo "[✓] Installation complete!"
    echo "Installed plugins: $(echo "$sels" | wc -l)"
fi
