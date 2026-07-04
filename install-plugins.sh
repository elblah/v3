#!/bin/bash

# install-plugins.sh - Install optional plugins from examples/plugins/
# Core plugins in aicoder/plugins/ are auto-loaded - no installation needed.

PLUGIN_SRC="examples/plugins"
PLUGIN_DST="$HOME/.config/aicoder-v3/plugins"

plugins=$(find "$PLUGIN_SRC" -name "*.py" | grep -v test_ | sort)

if [[ "$@" =~ --help ]]; then
    echo "--update  - update installed plugins"
    echo "--default - install all example plugins without selection"
    echo ""
    echo "Note: Core plugins (aicoder/plugins/) are auto-loaded on startup."
    echo "      This script installs optional plugins from examples/plugins/."
    exit
fi

if [[ "$@" =~ --update ]]; then
    tmp_sels=""
    while read -r plugin; do
        filename="${plugin##*/}"
        plug_inst_path="$PLUGIN_DST/${filename}"
        [[ ! -e "$plug_inst_path" ]] && continue
        if ! cmp "$plugin" "$plug_inst_path" &> /dev/null; then
            tmp_sels+="${plugin}\n"
        fi
    done <<< "$plugins"
    sels="$(printf "$tmp_sels")"
elif [[ "$@" =~ --default ]]; then
    sels=""
    while read -r plugin; do
        sels+="$plugin\n"
    done <<< "$plugins"
    sels="$(printf "$sels")"
else
    echo "Select plugins to install (use TAB to multi-select, ENTER to confirm):"
    sels=$(echo "$plugins" | fzf -m -e)
fi

[ -z "$sels" ] && exit 1

mkdir -p "$PLUGIN_DST"

while read -r LINE; do
    cp -v "$LINE" "$PLUGIN_DST/"
done <<< "$sels"

if [ -n "$sels" ]; then
    echo ""
    echo "[✓] Installation complete!"
    echo "Installed plugins: $(echo "$sels" | wc -l)"
fi