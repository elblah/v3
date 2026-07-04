#!/bin/bash
# install-skills.sh - Pick and install skills (local + remote)
# Local: examples/skills/
# Remote: GitHub repos (listed below)

SKILLS_DIR="$HOME/.config/aicoder-v3/skills"
PLUGINS_DIR="$HOME/.config/aicoder-v3/plugins"
AICODER_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$SKILLS_DIR"

# Check if skills plugin is installed
if [ ! -f "$PLUGINS_DIR/skills.py" ]; then
    echo ""
    echo "Note: The skills plugin (examples/plugins/skills.py) is not installed."
    echo "      The plugin loads skills automatically on startup."
    echo "      Without it you can still use skills by:"
    echo "        - Setting SKILLS_DIR env var (pointing to $SKILLS_DIR)"
    echo "        - Saying 'read skills dir at $SKILLS_DIR' in conversation"
    echo ""
    read -p "Install the skills plugin now? [y/N]: " ans
    if [[ "$ans" =~ [yY] ]]; then
        mkdir -p "$PLUGINS_DIR"
        cp -v "$AICODER_DIR/examples/plugins/skills.py" "$PLUGINS_DIR/"
        echo "[✓] skills plugin installed"
    else
        echo "Skipped. You can install later with: install-plugins.sh"
    fi
    echo ""
fi

# Remote skills: "display_name|user/repo|skill_dir_in_tarball"
REMOTE_SKILLS=(
    "caveman|JuliusBrussee/caveman|skills/caveman"
    "caveman-commit|JuliusBrussee/caveman|skills/caveman-commit"
    "caveman-review|JuliusBrussee/caveman|skills/caveman-review"
    "karpathy-guidelines|forrestchang/andrej-karpathy-skills|skills/karpathy-guidelines"
)

# Build fzf list
local_skills=$(find "$AICODER_DIR/examples/skills" -maxdepth 1 -mindepth 1 -type d -exec basename {} \; 2>/dev/null | sed 's/^/local:/')

remote_list=""
for entry in "${REMOTE_SKILLS[@]}"; do
    name="${entry%%|*}"
    remote_list+="remote:$entry"$'\n'
done
remote_list="${remote_list%$'\n'}"

choices=$(printf "%s\n%s" "$local_skills" "$remote_list" | fzf -m -e)

[ -z "$choices" ] && exit 1

install_local() {
    local name="$1"
    local src="$AICODER_DIR/examples/skills/$name"
    rm -rf "$SKILLS_DIR/$name"
    [ -d "$src" ] && cp -vR "$src" "$SKILLS_DIR/$name"
}

install_remote() {
    local entry="$1"
    local name="${entry%%|*}"
    local rest="${entry#*|}"
    local repo="${rest%%|*}"
    local path="${rest#*|}"

    echo -e "\e[32mInstalling remote: $name from $repo\e[0m"

    rm -rf "$SKILLS_DIR/$name"

    local tmpdir
    tmpdir=$(mktemp -d)
    tarball="$tmpdir/repo.tar.gz"

    curl -sfL "https://github.com/$repo/archive/refs/heads/main.tar.gz" -o "$tarball" || {
        echo "  \e[31mDownload failed\e[0m"
        rm -rf "$tmpdir"
        return 1
    }

    tar -xzf "$tarball" -C "$tmpdir" --wildcards "*/$path/*"

    # Find the extracted dir
    local extracted
    extracted=$(find "$tmpdir" -type d -name "$(basename "$path")" | head -1)
    if [ -d "$extracted" ]; then
        cp -vR "$extracted/." "$SKILLS_DIR/$name"
    else
        echo "  \e[31mPath not found: $path\e[0m"
        rm -rf "$tmpdir"
        return 1
    fi

    rm -rf "$tmpdir"
    echo -e "\e[32mInstalled: $name\e[0m"
}

while IFS= read -r line; do
    if [[ "$line" == local:* ]]; then
        name="${line#local:}"
        install_local "$name"
    elif [[ "$line" == remote:* ]]; then
        entry="${line#remote:}"
        install_remote "$entry"
    fi
done <<< "$choices"
