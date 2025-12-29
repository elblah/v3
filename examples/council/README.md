# Council Plugin

Get expert opinions from multiple AI perspectives on your code and work.

## Installation

1. **Install member files:**
   ```bash
   ./examples/council/install.sh
   ```

   This creates council member definitions in `.aicoder/council/` (project-specific)

2. **Or create your own:**
   ```bash
   mkdir -p .aicoder/council
   # Create member_*.txt files
   ```

## Usage

### Basic Council Query
```
/council <message>
```

Get opinions from all council members on your current work.

### Auto-Council Mode (Iterative)
```
/council --auto <spec.md>
```

Or open editor:
```
/council --auto
```

Council reviews each iteration and votes:
- `IMPLEMENTATION_FINISHED` - Implementation complete
- `IMPLEMENTATION_NOT_FINISHED` - Needs changes

Auto-iteration continues until all members vote FINISHED.

### Subcommands

| Command | Description |
|---------|-------------|
| `/council list` | Show available members |
| `/council current` | Show current council plan |
| `/council accept` | Inject plan into conversation |
| `/council clear` | Clear current session |
| `/council edit <name>` | Edit member file |
| `/council enable <name>` | Enable member |
| `/council disable <name>` | Disable member |
| `/council help` | Show help |

### Flags

| Flag | Description |
|------|-------------|
| `--direct` | Direct opinions (no moderator) |
| `--auto` | Enable auto-council mode |
| `--auto-continue` | Continue auto-council iteration |
| `--members m1,m2` | Use specific members |
| `--reset-context` | Fresh context each turn |
| `--no-reset` | Preserve context |

## Member Files

Member files are plain text files with system prompts.

Naming convention:
- `member_name_auto.txt` - Auto-council member (votes FINISHED/NOT_FINISHED)
- `member_name.txt` - Regular member
- `_disabled_member.txt` - Disabled (underscore prefix)

### Auto-Mode Member Template

For auto-mode members (`*_auto.txt`), the plugin automatically adds generic voting instructions. Keep your member file simple:

```
You are a Role Name.

Your role is to describe what you check.

Check for:
- Criteria 1
- Criteria 2
```

The plugin will automatically append voting instructions (FINISHED/NOT_FINISHED) and word limits.

### Regular Member Template

```
You are a Role Name.

Your role is to describe what you do.

Provide your expert opinion on the code/work.
Focus on: [specific areas]

Be concise and helpful.
```

### Moderator

```
You are a Council Moderator.

Your role is to synthesize expert opinions into clear, actionable feedback.

When you receive multiple opinions:
1. Identify common themes and priorities
2. Note any conflicting feedback
3. Create a prioritized list of actions
4. Provide a concise summary
```

## Configuration

Environment variables:

- `COUNCIL_MAX_ITERATIONS` - Max auto-council iterations (default: 10)
- `EDITOR` - Editor for `/council edit` and `/council --auto` (default: vim)

## Project-Specific Council

Council members are always project-specific in `.aicoder/council/`. Each project can have its own set of members.

To set up council for a project:
1. Run `./examples/council/install.sh` in the project root
2. Or manually create `.aicoder/council/` and add member files

## Examples

### Quick Review
```
/council Review this function for bugs and improvements
```

### Auto-Council with Spec
```
/council --auto "Implement a REST API with CRUD operations"
```

The AI will implement, then council reviews, then AI refines, until complete.

### Use Specific Members
```
/council --members security,ux Check this web page
```
