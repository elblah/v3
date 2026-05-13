#!/bin/bash

# AI Coder Configuration Tool
# fdisk-style single-letter command prompt
# Zero external deps: uses read -e, fzf only if available

AICODER_BIN="${AICODER_BIN:-aicoder-v3}"
INSTALL_DIR() { echo "${AICODER_INSTALL_DIR:-$HOME/.local/bin}"; }
SKILLS_DIR="$HOME/.config/aicoder-v3/skills"
PLUGINS_DIR="$HOME/.config/aicoder-v3/plugins"
LOCAL_SKILLS_DIR=".aicoder/skills"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# GitHub fallback for when running piped (not from repo)
GITHUB_RAW="https://raw.githubusercontent.com/elblah/v3/master"
GITHUB_REPO="https://api.github.com/repos/elblah/v3"

# List files from local dir or GitHub API
_list_files() {
    local local_dir=$1 github_path=$2 suffix=$3
    if [ -d "$local_dir" ]; then
        for f in "$local_dir"/*; do
            [ -f "$f" ] || continue
            basename "$f"
        done
    else
        curl -fsSL "$GITHUB_REPO/contents/$github_path" 2>/dev/null \
            | python3 -c "
import sys,json
for item in json.load(sys.stdin):
    name = item.get('name', '')
    if name.endswith('$suffix'):
        print(name)
" 2>/dev/null
    fi
}

# Download a file from local dir or GitHub
_get_file() {
    local src_dir=$1 github_path=$2 filename=$3 dest=$4
    local local_file="$src_dir/$filename"
    if [ -f "$local_file" ]; then
        cp "$local_file" "$dest"
    else
        curl -fsSL "$GITHUB_RAW/$github_path/$filename" -o "$dest"
    fi
}

# Read from terminal even when piped (stdin is script content)
_read() {
    if [ -t 0 ]; then
        read "$@"
    elif ( : </dev/tty ) 2>/dev/null; then
        read "$@" </dev/tty
    fi
}

R="\033[0m"; G="\033[32m"; Y="\033[33m"; C="\033[36m"; B="\033[1m"; DIM="\033[2m"

# Check if aicoder binary exists, offer install if not
if ! command -v "$AICODER_BIN" &>/dev/null; then
    echo -e "${Y}Warning:${R} '$AICODER_BIN' not found in PATH"
    echo ""
    echo "Install it with:"
    echo -e "  ${C}uv tool install git+https://github.com/elblah/v3${R}"
    echo ""
    _read -p "Install now? [y/N]: " ans
    if [[ "$ans" =~ [yY] ]]; then
        if ! command -v uv &>/dev/null; then
            echo -e "${Y}uv not found. Installing...${R}"
            curl -fsSL https://astral.sh/uv/install.sh | sh
        fi
        if command -v uv &>/dev/null; then
            uv tool install git+https://github.com/elblah/v3
            if command -v "$AICODER_BIN" &>/dev/null; then
                echo -e "${G}Installed:${R} $AICODER_BIN"
            else
                echo -e "${Y}Install may have failed. Set AICODER_BIN env if binary name differs.${R}"
            fi
        else
            echo "uv not available. Install manually:"
            echo "  curl -fsSL https://astral.sh/uv/install.sh | sh"
            echo "  uv tool install git+https://github.com/elblah/v3"
        fi
    fi
    echo ""
fi

sleep 1

show_menu() {
    clear
    echo -e "${B}AI Coder Configuration Tool${R}  v0.1"
    echo ""
    echo "Main menu:"
    echo ""
    echo -e "  ${G}c${R}  Create launch script"
    echo -e "  ${G}p${R}  Plugin management"
    echo -e "  ${G}s${R}  Skills management"
    echo -e "  ${G}n${R}  Install all snippets"
    echo -e "  ${G}u${R}  Update aicoder via uv"
    echo -e "  ${G}q${R}  Quit"
    echo ""
}

# Provider presets
declare -A PRESETS
PRESETS[1,name]="OpenAI (OpenAI-compatible)"
PRESETS[1,api]="openai"; PRESETS[1,ep]="https://api.openai.com/v1"
PRESETS[1,model]="gpt-4o"; PRESETS[1,ctx]="128000"; PRESETS[1,prov]=""

PRESETS[2,name]="MiniMax (Anthropic API)"
PRESETS[2,api]="anthropic"; PRESETS[2,ep]="https://api.minimax.io/anthropic/v1/messages"
PRESETS[2,model]="MiniMax-M2.7"; PRESETS[2,ctx]="200000"; PRESETS[2,prov]="anthropic"

PRESETS[3,name]="OpenRouter"
PRESETS[3,api]="openai"; PRESETS[3,ep]="https://openrouter.ai/api/v1"
PRESETS[3,model]="anthropic/claude-sonnet-4-20250514"; PRESETS[3,ctx]="200000"; PRESETS[3,prov]=""

PRESETS[4,name]="Nvidia NIM"
PRESETS[4,api]="openai"; PRESETS[4,ep]="https://integrate.api.nvidia.com/v1"
PRESETS[4,model]="meta/llama-3.1-405b-instruct"; PRESETS[4,ctx]="128000"; PRESETS[4,prov]=""

PRESETS[5,name]="Opencode Zen"
PRESETS[5,api]="openai"; PRESETS[5,ep]="https://api.zen.ci/v1"
PRESETS[5,model]="gpt-4o-mini"; PRESETS[5,ctx]="128000"; PRESETS[5,prov]=""

# read_edit <label> <default>
# Sets $EDIT_RESULT. Returns non-zero on Ctrl+C.
# Uses -i to prefill the field with default for easy editing.
read_edit() {
    local label=$1 default=$2 input
    if [ -n "$default" ]; then
        _read -e -p "${label}: " -i "$default" input || return $?
    else
        _read -e -p "${label}: " input || return $?
    fi
    EDIT_RESULT="$input"
}

test_connection() {
    local api=$1 ep=$2 key=$3 mod=$4 resp
    echo ""; echo -e "${DIM}Testing...${R}"
    local data='{"model":"'$mod'","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
    if [ "$api" = "anthropic" ]; then
        local hdr=()
        [ -n "$key" ] && hdr=(-H "x-api-key: $key" -H "anthropic-version: 2023-06-01")
        resp=$(curl -s -o /dev/null -w "%{http_code}" -H "Content-Type: application/json" \
            "${hdr[@]}" -d "$data" "$ep" 2>/dev/null)
    else
        local chat_ep="${ep}/chat/completions"
        local hdr=()
        [ -n "$key" ] && hdr=(-H "Authorization: Bearer $key")
        resp=$(curl -s -o /dev/null -w "%{http_code}" -H "Content-Type: application/json" \
            "${hdr[@]}" -d "$data" "$chat_ep" 2>/dev/null)
    fi
    if [ "$resp" = "200" ] || [ "$resp" = "201" ]; then
        echo -e "  ${G}OK${R} (HTTP $resp)"
    else
        echo -e "  ${Y}HTTP $resp${R} (may still work)"
    fi
}

generate_script() {
    local fp=$1 api=$2 ep=$3 key=$4 mod=$5 ctx=$6 temp=$7 top_p=$8 top_k=$9 prov=$10
    mkdir -p "$(dirname "$fp")"

    cat > "$fp" << ENDSCRIPT
#!/bin/bash
# Launch: ${api} | ${mod}

export OPENAI_API_KEY="${key}"
export API_KEY="${key}"
ENDSCRIPT

    if [ "$api" = "anthropic" ]; then
        cat >> "$fp" << ENDSCRIPT
export API_PROVIDER="anthropic"
export API_ENDPOINT="${ep}"
ENDSCRIPT
    else
        cat >> "$fp" << ENDSCRIPT
export OPENAI_BASE_URL="${ep}"
export API_BASE_URL="${ep}"
ENDSCRIPT
    fi

    cat >> "$fp" << ENDSCRIPT
export API_MODEL="${mod}"
export OPENAI_MODEL="${mod}"
export CONTEXT_SIZE="${ctx}"
ENDSCRIPT

    [ -n "$temp" ] && echo "export TEMPERATURE=${temp}" >> "$fp"
    [ -n "$top_p" ] && echo "export TOP_P=${top_p}" >> "$fp"
    [ -n "$top_k" ] && echo "export TOP_K=${top_k}" >> "$fp"

    cat >> "$fp" << ENDSCRIPT

exec ${AICODER_BIN} "\$@"
ENDSCRIPT

    chmod +x "$fp"
    echo ""; echo -e "${G}Created:${R} ${B}$fp${R}"
    local d=$(dirname "$fp")
    if ! echo "$PATH" | grep -q "$d"; then
        echo -e "${Y}Add to PATH:${R} export PATH=\$PATH:$d"
    fi
}

name_and_gen() {
    local api=$1 ep=$2 key=$3 mod=$4 ctx=$5 temp=$6 top_p=$7 top_k=$8 prov=$9
    local mslug=$(echo "$mod" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g;s/--*/-/g;s/^-//;s/-$//')
    local default_name="${prov:+aicoder-${prov}-${mslug}}"
    [ -z "$default_name" ] && default_name="aicoder-${api}-${mslug}"

    local default_path="$(INSTALL_DIR)/$default_name"
    read_edit "Script path" "$default_path" || return; local spath=${EDIT_RESULT:-$default_path}

    echo ""; _read -p "Test connection? [y/N]: " do_test
    [[ "$do_test" =~ [yY] ]] && test_connection "$api" "$ep" "$key" "$mod"

    generate_script "$spath" "$api" "$ep" "$key" "$mod" "$ctx" "$temp" "$top_p" "$top_k" "$prov"
}

use_preset() {
    local n=$1
    local api="${PRESETS[$n,api]}" ep="${PRESETS[$n,ep]}" model="${PRESETS[$n,model]}"
    local ctx="${PRESETS[$n,ctx]}" prov="${PRESETS[$n,prov]}"

    clear
    echo -e "${B}${PRESETS[$n,name]}${R}"
    echo ""

    local ep_v key_v mod_v ctx_v temp_v top_p_v top_k_v
    read_edit "Endpoint" "$ep" || return; ep_v=${EDIT_RESULT:-$ep}
    read_edit "API key" "" || return; key_v=$EDIT_RESULT
    read_edit "Model" "$model" || return; mod_v=${EDIT_RESULT:-$model}
    read_edit "Context size" "$ctx" || return; ctx_v=${EDIT_RESULT:-$ctx}
    read_edit "Temperature" "" || return; temp_v=$EDIT_RESULT
    read_edit "Top P" "" || return; top_p_v=$EDIT_RESULT
    read_edit "Top K" "" || return; top_k_v=$EDIT_RESULT

    name_and_gen "$api" "$ep_v" "$key_v" "$mod_v" "$ctx_v" "$temp_v" "$top_p_v" "$top_k_v" "$prov"
}

custom_provider() {
    clear; echo -e "${B}Custom provider${R}"; echo ""

    local api ep key mod ctx temp top_p top_k prov=""
    read_edit "API type [openai/anthropic]" "openai" || return; api=${EDIT_RESULT:-openai}
    read_edit "Endpoint" "" || return; ep=$EDIT_RESULT; [ -z "$ep" ] && return
    read_edit "API key" "" || return; key=$EDIT_RESULT
    read_edit "Model" "" || return; mod=$EDIT_RESULT; [ -z "$mod" ] && { echo "Model required"; sleep 1; return; }
    read_edit "Context size" "128000" || return; ctx=$EDIT_RESULT
    read_edit "Temperature" "" || return; temp=$EDIT_RESULT
    read_edit "Top P" "" || return; top_p=$EDIT_RESULT
    read_edit "Top K" "" || return; top_k=$EDIT_RESULT
    [ "$api" = "anthropic" ] && prov="anthropic"

    name_and_gen "$api" "$ep" "$key" "$mod" "$ctx" "$temp" "$top_p" "$top_k" "$prov"
}

cmd_create() {
    while true; do
        clear; echo -e "${B}Create launch script${R}"; echo ""
        echo "Select provider:"
        for i in 1 2 3 4 5 6; do
            [ "$i" -eq 6 ] && echo -e "  ${G}6${R}  Custom" || echo -e "  ${G}$i${R}  ${PRESETS[$i,name]}"
        done
        echo -e "  ${G}m${R}  Main menu"
        echo ""
        _read -p "Select (1-6, m=menu): " sel
        case "$sel" in
            1|2|3|4|5) use_preset "$sel" ;;
            6) custom_provider ;;
            m|q) return ;;
        esac
    done
}

cmd_plugins() {
    local avail_dir="$PROJECT_ROOT/plugins"
    local github_path="plugins"
    while true; do
        clear; echo -e "${B}Plugin management${R}"; echo ""
        echo -e "${DIM}Plugins:${R}"
        local avail=()
        while IFS= read -r f; do
            [ -z "$f" ] || [[ "$f" != *.py ]] && continue
            local n=$(basename "$f" .py)
            avail+=("$n")
            if [ -f "$PLUGINS_DIR/$n.py" ]; then
                if [ -d "$avail_dir" ] && [ -f "$avail_dir/$n.py" ] \
                    && ! cmp -s "$avail_dir/$n.py" "$PLUGINS_DIR/$n.py"; then
                    printf "  ${Y}[U]${R} %s\n" "$n"
                else
                    printf "  ${G}[X]${R} %s\n" "$n"
                fi
            else
                printf "  ${DIM}[ ]${R} %s\n" "$n"
            fi
        done < <(_list_files "$avail_dir" "$github_path" "\\.py$")
        echo ""
        echo -e "  ${G}e <name>${R}  Enable (copy to ~/.config/aicoder-v3/plugins/)"
        echo -e "  ${G}d <name>${R}  Disable (remove from ~/.config/aicoder-v3/plugins/)"
        echo -e "  ${G}u${R}         Update all installed plugins"
        echo -e "  ${G}m${R}         Main menu"
        echo ""
        _read -p "Command: " cmd args
        case "$cmd" in
            m|q) return ;;
            e)
                [ -z "$args" ] && { echo -n "Plugin: "; _read args; }
                mkdir -p "$PLUGINS_DIR"
                _get_file "$avail_dir" "$github_path" "${args}.py" "$PLUGINS_DIR/${args}.py" 2>/dev/null
                if [ -f "$PLUGINS_DIR/${args}.py" ]; then
                    echo -e "${G}Enabled:${R} $args"
                else
                    echo -e "${Y}Not found:${R} $args"
                fi
                sleep 1 ;;
            d)
                [ -z "$args" ] && { echo -n "Plugin: "; _read args; }
                if [ -f "$PLUGINS_DIR/$args.py" ]; then
                    rm "$PLUGINS_DIR/$args.py"
                    echo "Disabled: $args"
                else
                    echo -e "${Y}Not enabled:${R} $args"
                fi
                sleep 1 ;;
            u)
                local updated=0
                for f in "$PLUGINS_DIR"/*.py; do
                    [ -f "$f" ] || continue
                    local name=$(basename "$f")
                    if [ -d "$avail_dir" ]; then
                        local src="$avail_dir/$name"
                        [ -f "$src" ] || continue
                        if ! cmp -s "$f" "$src"; then
                            cp "$src" "$f"
                            echo -e "  ${G}✓${R} $name"
                            updated=$((updated + 1))
                        fi
                    else
                        curl -fsSL "$GITHUB_RAW/$github_path/$name" -o "$f.tmp" 2>/dev/null \
                            && mv "$f.tmp" "$f" \
                            && echo -e "  ${G}✓${R} $name" \
                            && updated=$((updated + 1)) \
                            || rm -f "$f.tmp"
                    fi
                done
                echo -e "${G}Updated $updated plugins${R}"
                sleep 1 ;;
        esac
    done
}

cmd_skills() {
    while true; do
        clear; echo -e "${B}Skills management${R}"; echo ""
        echo -e "${DIM}Installed:${R}"
        local found=0
        for d in "$SKILLS_DIR" "$LOCAL_SKILLS_DIR"; do
            [ -d "$d" ] || continue
            for skill in "$d"/*/; do
                [ -d "$skill" ] || continue
                local name=$(basename "$skill")
                local desc=$(grep -m1 'description:' "$skill/SKILL.md" 2>/dev/null | sed 's/description: *//')
                echo -e "  ${G}•${R} ${B}$name${R}${desc:+: $desc}"
                found=1
            done
        done
        [ "$found" -eq 0 ] && echo "  (none)"
        echo ""
        echo -e "  ${G}i${R}  Install from examples/skills/"
        echo -e "  ${G}r <name>${R}  Remove"
        echo -e "  ${G}m${R}  Main menu"
        echo ""
        _read -p "Command: " cmd args
        case "$cmd" in
            m|q) return ;;
            i)
                local ex="$PROJECT_ROOT/examples/skills"
                echo ""; echo "Available:"
                if [ -d "$ex" ]; then
                    for d in "$ex"/*/; do
                        [ -d "$d" ] || continue
                        local n=$(basename "$d"); echo "  $n"
                    done
                else
                    curl -fsSL "$GITHUB_REPO/contents/examples/skills" 2>/dev/null \
                        | python3 -c "
import sys,json
for item in json.load(sys.stdin):
    if item.get('type') == 'dir':
        print(item.get('name', ''))
" 2>/dev/null | sort
                fi
                echo ""
                _read -p "Install: " sn
                if [ -d "$ex/$sn" ]; then
                    mkdir -p "$SKILLS_DIR"; rm -rf "$SKILLS_DIR/$sn"
                    cp -r "$ex/$sn" "$SKILLS_DIR/"
                    echo -e "${G}Installed:${R} $sn"
                elif [ -z "$ex" ] && [ -n "$sn" ]; then
                    echo -e "${Y}Remote skill install not yet supported${R}"
                else
                    echo -e "${Y}Not found:${R} $sn"
                fi
                sleep 1 ;;
            r)
                [ -z "$args" ] && { echo -n "Skill: "; _read args; }
                if [ -d "$SKILLS_DIR/$args" ]; then rm -rf "$SKILLS_DIR/$args"; echo "Removed: $args"
                elif [ -d "$LOCAL_SKILLS_DIR/$args" ]; then rm -rf "$LOCAL_SKILLS_DIR/$args"; echo "Removed: $args"
                else echo -e "${Y}Not found:${R} $args"
                fi
                sleep 1 ;;
        esac
    done
}

cmd_snippets() {
    local src="$PROJECT_ROOT/examples/snippets"
    local dst="$HOME/.config/aicoder-v3/snippets"
    local count=0
    mkdir -p "$dst"
    if [ -d "$src" ]; then
        for f in "$src"/*; do
            [ -f "$f" ] || continue
            cp "$f" "$dst/"
            count=$((count + 1))
        done
    else
        curl -fsSL "$GITHUB_REPO/contents/examples/snippets" 2>/dev/null \
            | python3 -c "
import sys,json
for item in json.load(sys.stdin):
    name = item.get('name', '')
    if name.endswith('.md'):
        print(name)
" 2>/dev/null | while IFS= read -r fname; do
            [ -z "$fname" ] && continue
            curl -fsSL "$GITHUB_RAW/examples/snippets/$fname" -o "$dst/$fname" 2>/dev/null
            [ -f "$dst/$fname" ] && count=$((count + 1))
        done
    fi
    echo -e "${G}Installed $count snippets${R} to $dst"
    sleep 1
}

cmd_update_aicoder() {
    if ! command -v uv &>/dev/null; then
        echo -e "${Y}uv not found${R}"
        _read -p "Install uv via https://astral.sh/uv/install.sh? [y/N]: " ans
        if [[ "$ans" =~ [yY] ]]; then
            curl -fsSL https://astral.sh/uv/install.sh | sh
        fi
    fi
    if command -v uv &>/dev/null; then
        echo ""
        echo -e "${DIM}Running: uv tool upgrade ${AICODER_BIN}${R}"
        echo ""
        uv tool upgrade "$AICODER_BIN" 2>&1 || true
    else
        echo "uv not available. Install manually:"
        echo "  curl -fsSL https://astral.sh/uv/install.sh | sh"
    fi
    echo ""
    _read -p "Press Enter"
}

# ---- Self-install ----
if [ "$1" = "--install" ] || [ "$1" = "-i" ]; then
    local_dir=$(INSTALL_DIR)
    mkdir -p "$local_dir"
    # If running from a real file, copy it; otherwise download from GitHub
    if [ -f "$0" ] && [ "$0" != "bash" ]; then
        cp "$0" "$local_dir/aicoder-config"
    else
        echo "Downloading aicoder-config..."
        curl -fsSL "https://raw.githubusercontent.com/elblah/v3/master/aicoder-config.sh" \
            -o "$local_dir/aicoder-config"
    fi
    chmod +x "$local_dir/aicoder-config"
    echo -e "${G}Installed:${R} $local_dir/aicoder-config"
    exit 0
fi

# ---- Main entry point (only runs when executed, not sourced) ----
if [ -z "${BASH_SOURCE[0]}" ] || [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    while true; do
        show_menu
        _read -p "Command: " cmd
        case "$cmd" in
            c) cmd_create ;; n) cmd_snippets ;; p) cmd_plugins ;; s) cmd_skills ;;
            u) cmd_update_aicoder ;; q) clear; exit 0 ;;
            *) echo "Unknown"; sleep 1 ;;
        esac
    done
fi
