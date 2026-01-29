#!/bin/bash

snippets=$(find examples/snippets -type f)

if [[ "$@" =~ --all ]]; then
    sels="$snippets"
else
    sels=$(echo "$snippets" | fzf -m -e)
fi

[ -z "$sels" ] && exit 1

mkdir -p ~/.config/aicoder-v3/snippets

# Get the aicoder source directory
AICODER_DIR=$(cd "$(dirname "$0")" && pwd)

while read -r LINE; do
    cp -v "$LINE" ~/.config/aicoder-v3/snippets/"$filename"
done <<< "$sels"
