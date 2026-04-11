#!/bin/bash
# install-skills.sh - Pick and install skills (local + remote)
# Local: examples/skills/
# Remote: GitHub repos (listed below)

SKILLS_DIR="$HOME/.config/aicoder-v3/skills"
AICODER_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$SKILLS_DIR"

# Remote skills: "display_name|user/repo|skill_dir_in_tarball"
REMOTE_SKILLS=(
    "caveman|JuliusBrussee/caveman|skills/caveman"
    "caveman-commit|JuliusBrussee/caveman|skills/caveman-commit"
    "caveman-review|JuliusBrussee/caveman|skills/caveman-review"
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
    [ -d "$src" ] && cp -vR "$src" "$SKILLS_DIR/$name"
}

install_remote() {
    local entry="$1"
    local name="${entry%%|*}"
    local rest="${entry#*|}"
    local repo="${rest%%|*}"
    local path="${rest#*|}"

    echo -e "\e[32mInstalling remote: $name from $repo\e[0m"

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