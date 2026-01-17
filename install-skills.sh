#!/bin/bash

skills=$(find examples/skills -maxdepth 1 -mindepth 1 -type d)

sels=$(echo "$skills" | fzf -m -e)

[ -z "$sels" ] && exit 1

mkdir -p ~/.config/aicoder-v3/skills

# Get the aicoder source directory
AICODER_DIR=$(cd "$(dirname "$0")" && pwd)

while read -r LINE; do
    echo -e "\e[32mInstalling: $LINE\e[0m"
    cp -vR "$LINE" ~/.config/aicoder-v3/skills/"$filename"
done <<< "$sels"
