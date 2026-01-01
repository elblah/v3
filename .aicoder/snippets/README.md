# Snippets Plugin

A minimalist plugin for reusable prompt snippets in AI Coder.

## Features

- **Tab completion**: Type `@@` and press Tab to see available snippets
- **Automatic replacement**: Snippets are automatically replaced with file content
- **Multiple sources**: Project-specific snippets (`.aicoder/snippets/`) and global snippets (`~/.config/aicoder-v3/snippets/`)
- **Lightweight caching**: Fast snippet lookup with automatic cache refresh
- **Error handling**: Clear warnings when snippets are not found

## Installation

The plugin is already installed in `.aicoder/plugins/snippets.py`.

## Usage

### Create Snippets

Place files in `.aicoder/snippets/` (project-specific) or `~/.config/aicoder-v3/snippets/` (global):

```
.aicoder/snippets/
├── ultrathink.md
├── plan_mode.txt
├── build_mode.txt
├── debug_mode.md
└── rethink
```

### Use Snippets in Prompts

Reference snippets in your prompts using `@@` prefix:

```
Use @@ultrathink to analyze the code
```

When you press Enter, `@@ultrathink` is replaced with the contents of `ultrathink.md`.

### Tab Completion

Type `@@` and press Tab to see available snippets:

```
> @@<Tab>
@@build_mode.txt  @@debug_mode.md  @@plan_mode.txt  @@rethink  @@ultrathink.md
```

### List Available Snippets

Use the `/snippets` command to list all available snippets:

```
> /snippets
Available snippets (project):
  - build_mode.txt
  - debug_mode.md
  - plan_mode.txt
  - rethink
  - ultrathink.md
```

## Snippet Directory Priority

1. `.aicoder/snippets/` (project) - takes precedence
2. `~/.config/aicoder-v3/snippets/` (global) - fallback

## Snippet File Formats

Any text file format is supported:
- `.md` (Markdown)
- `.txt` (Plain text)
- No extension (Plain text)

Example snippet files are provided.

## Snippet Replacement Behavior

- **Valid snippet**: `@@snippet_name` → [file content]
- **Invalid snippet**: Warning displayed, original `@@snippet_name` preserved
- **Multiple snippets**: All `@@` references are replaced
- **Works everywhere**: Readline, stdin, `/edit` command, socket API

## Technical Details

### Hooks

The plugin registers an `after_user_prompt` hook that transforms the prompt before it's sent to the AI.

### Completers

The plugin registers a completer function that activates on `@@` prefix.

### Caching

Snippet files are cached with mtime-based invalidation. The cache refreshes automatically when:
- Directory mtime changes
- Different directory is used (project vs global)
