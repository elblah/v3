# Snippets Plugin - Quick Start Guide

## What is it?

A minimalist plugin that lets you reuse prompt snippets stored as files.

## Quick Start

### 1. Try Tab Completion

Run AI Coder and type `@@` then press Tab:

```bash
python main.py
> @@<Tab>
@@build_mode.txt  @@debug_mode.md  @@plan_mode.txt  @@rethink  @@ultrathink.md
```

### 2. Use a Snippet

Include a snippet in your prompt:

```bash
> Use @@ultrathink to analyze this code
```

When you press Enter, `@@ultrathink` is automatically replaced with the full content of `ultrathink.md`.

### 3. List Available Snippets

```bash
> /snippets
Available snippets (project):
  - build_mode.txt
  - debug_mode.md
  - plan_mode.txt
  - rethink
  - ultrathink.md
```

## What Snippets Are Available?

| Snippet | Description |
|---------|-------------|
| `ultrathink.md` | Senior developer persona with YAGNI principles |
| `plan_mode.txt` | Structured planning methodology |
| `build_mode.txt` | Implementation guidelines and best practices |
| `debug_mode.md` | Systematic debugging approach |
| `rethink` | Prompts to reconsider assumptions |

## Creating Your Own Snippets

1. Create a text file in `.aicoder/snippets/`:
   ```bash
   echo "Your custom instructions here" > .aicoder/snippets/my_snippet.txt
   ```

2. Use it immediately:
   ```bash
   > Use @@my_snippet.txt to solve this problem
   ```

## How It Works

- **Snippets are files** - Any text file in `.aicoder/snippets/` is a snippet
- **Automatic replacement** - `@@snippet_name` is replaced with file content
- **Works everywhere** - Readline, stdin, `/edit` command, socket API
- **Lightweight caching** - Fast lookup, auto-refreshes on changes

## Tips

- Use `.md` or `.txt` extensions for clarity (but any extension works)
- No extension is also supported (like `rethink`)
- Project snippets (`.aicoder/snippets/`) take precedence over global (`~/.config/aicoder-v3/snippets/`)
- Use multiple snippets in one prompt: `Use @@plan_mode and @@debug_mode`

## Technical Details

- **Plugin location**: `plugins/snippets.py`
- **Installed in**: `.aicoder/plugins/snippets.py`
- **Core changes**: Only ~70 lines across 3 core files
- **No dependencies**: Uses only Python stdlib

## Getting Help

- List snippets: `/snippets`
- Read documentation: `.aicoder/snippets/README.md`
- Technical details: `SNIPPETS_IMPLEMENTATION.md`
