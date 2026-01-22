#!/bin/bash

plugins=$(find plugins -name "*.py" | grep -v test_)

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
