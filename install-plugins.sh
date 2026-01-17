#!/bin/bash

echo "Select plugins to install (use TAB to multi-select, ENTER to confirm):"

plugins=$(find plugins -name "*.py" | grep -v test_)

sels=$(echo "$plugins" | fzf -m -e)

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
