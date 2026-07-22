#!/bin/bash
# install-skills.sh - Pick and install skills (local + remote)
# Local: examples/skills/
# Remote: GitHub repos (listed below)

BASE_DIR="$HOME/.config/aicoder-v3"
SKILLS_DIR="$BASE_DIR/skills"
SKILLS_EXTRA_DIR="$BASE_DIR/skills-extra"
AICODER_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$SKILLS_DIR" "$SKILLS_EXTRA_DIR"

# Remote skills: "display_name|user/repo|skill_dir_in_tarball"
REMOTE_SKILLS=(
    "ponytail|DietrichGebert/ponytail|skills/ponytail"
    "ponytail-audit|DietrichGebert/ponytail|skills/ponytail-audit"
    "ponytail-debt|DietrichGebert/ponytail|skills/ponytail-debt"
    "ponytail-gain|DietrichGebert/ponytail|skills/ponytail-gain"
    "ponytail-review|DietrichGebert/ponytail|skills/ponytail-review"
    "hallmark|nutlope/hallmark|skills/hallmark"
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

echo ""
echo "Install mode:"
echo "  [A]utoloaded  → ~/.config/aicoder-v3/skills/         (loaded every session)"
echo "  [E]xtra       → ~/.config/aicoder-v3/skills-extra/   (not auto-loaded)"
read -p "Choice [A/e]: " mode
if [[ "$mode" =~ [eE] ]]; then
    SKILLS_DIR="$SKILLS_EXTRA_DIR"
    echo "Installing to skills-extra/ (not auto-loaded)"
else
    echo "Installing to skills/ (auto-loaded)"
fi
echo ""

install_local() {
    local name="$1"
    local src="$AICODER_DIR/examples/skills/$name"
    rm -rf "$BASE_DIR/skills/$name" "$SKILLS_EXTRA_DIR/$name"
    [ -d "$src" ] && cp -vR "$src" "$SKILLS_DIR/$name"
}

install_remote() {
    local entry="$1"
    local name="${entry%%|*}"
    local rest="${entry#*|}"
    local repo="${rest%%|*}"
    local path="${rest#*|}"

    echo -e "\e[32mInstalling remote: $name from $repo\e[0m"

    rm -rf "$BASE_DIR/skills/$name" "$SKILLS_EXTRA_DIR/$name"

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
