# Ralph Plugin

Simple self-referential AI loops for iterative development.

## What is Ralph?

Ralph is a simple loop where the same prompt is fed repeatedly to an AI until completion. The AI sees its previous work in files and git history each iteration, allowing self-correction and refinement.

**Named after**: Ralph Wiggum from The Simpsons - embodies the philosophy of persistent iteration.

## How It Works

```bash
/ralph "Build a REST API for todos"

# AI works...
# Same prompt fed back...
# AI sees its previous work...
# Loop repeats until completion
```

The loop happens inside your session - no external bash loops needed.

## Quick Start

```bash
/ralph "Your task description"
```

That's it! The loop will run forever until:
- AI outputs `<promise>IMPLEMENTATION_FINISHED</promise>`
- You run `/ralph-cancel`

## Usage

### Start Loop

```bash
/ralph "Build a password validator"
```

**Options:**
- `--max-iterations N` - Stop after N iterations (default: unlimited)
- `--completion-promise "TEXT"` - Completion phrase (default: IMPLEMENTATION_FINISHED)

**Examples:**
```bash
/ralph "Fix the auth bug" --max-iterations 20
/ralph "Refactor code" --completion-promise "DONE"
/ralph "Create tests" --completion-promise "ALL_TESTS_PASSING"
```

### Cancel Loop

```bash
/ralph-cancel
```

## Completion Detection

To stop the loop, the AI must output:

```
<promise>YOUR_PHRASE</promise>
```

**Default:**
```
<promise>IMPLEMENTATION_FINISHED</promise>
```

**Custom:**
```bash
/ralph "task" --completion-promise "TASK_COMPLETE"

# AI outputs:
<promise>TASK_COMPLETE</promise>
```

## Prompt Writing Tips

### 1. Clear Completion Criteria

❌ Bad: "Build a todo API and make it good."

✅ Good:
```
Build a REST API for todos.

Requirements:
- CRUD endpoints working
- Input validation
- Tests passing

Output <promise>IMPLEMENTATION_FINISHED</promise> when complete.
```

### 2. Self-Correction Instructions

❌ Bad: "Implement feature X."

✅ Good:
```
Implement feature X using TDD:
1. Write failing tests
2. Implement feature
3. Run tests
4. Fix failures
5. Repeat until all green
6. Output <promise>IMPLEMENTATION_FINISHED</promise>
```

### 3. Incremental Goals

❌ Bad: "Build an e-commerce platform."

✅ Good:
```
Phase 1: Authentication (JWT, tests)
Phase 2: Product catalog (list, search, tests)
Phase 3: Shopping cart (add, remove, tests)

Output <promise>IMPLEMENTATION_FINISHED</promise> when done.
```

### 4. Safety Limits

Always use `--max-iterations` as a safety net:

```bash
/ralph "Try to implement feature X" --max-iterations 20
```

## When to Use Ralph

**Good for:**
- Well-defined tasks with clear success criteria
- Getting tests to pass (green → red → green cycle)
- Incremental feature implementation
- Refactoring with test-driven iteration
- Tasks requiring automatic verification

**Not good for:**
- Tasks requiring human judgment
- One-shot operations
- Tasks with unclear success criteria
- Complex design decisions
- Production debugging (use targeted debugging instead)

## Comparison with Council

| Feature | Ralph | Council |
|---------|-------|---------|
| **Complexity** | Simple loop | Multi-member coordination |
| **Experts** | 1 AI | Multiple experts |
| **Feedback** | Self-referential | Expert opinions |
| **Completion** | Promise detection | Unanimous voting |
| **Use case** | Task completion | Code review, quality gates |

**Use Ralph when**: You want simple iteration on a single task.
**Use Council when**: You want expert review and quality oversight.

## Real-World Examples

### Get Tests to Pass

```bash
/ralph "Make all tests pass for the password validator"
```

AI will:
1. Run tests → see failures
2. Fix bugs → run tests
3. See failures → iterate
4. All pass → output completion promise

### Implement Feature

```bash
/ralph "Implement user authentication with JWT tokens" --max-iterations 30
```

AI will:
1. Implement auth → write tests
2. Run tests → fix failures
3. Refactor → run tests
4. Iterate until max iterations or completion

### Refactor Code

```bash
/ralph "Refactor the cache layer to use LRU eviction" --completion-promise "REFACTOR_COMPLETE"
```

## Safety Features

- **Max iterations**: Always set to prevent infinite loops
- **Cancel command**: `/ralph-cancel` to stop anytime
- **Exact promise matching**: Prevents false completion

## Philosophy

Ralph embodies key principles:

1. **Iteration > Perfection**: Don't aim for perfect on first try
2. **Self-Correction**: Failures are data for improvement
3. **Persistence**: Keep trying until success
4. **Simplicity**: Same prompt, different outcome each time

## References

- Original technique: https://ghuntley.com/ralph/
- Claude Code implementation: `/github/claude-code/plugins/ralph-wiggum`
