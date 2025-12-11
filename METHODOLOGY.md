# Python Port Methodology

## Overview
This document describes the systematic approach for porting the AI Coder TypeScript implementation to Python, following the Anthropic long-running agent methodology.

## Core Problem
The Python port is a complex, multi-session task that spans many files and requires exact behavior matching. Previous attempts failed due to:
- Overengineering and losing track of progress
- Declaring components "complete" prematurely
- Inconsistent implementation across sessions
- No systematic verification

## Solution: Anthropic-Inspired Approach

### 1. Initializer Phase (One-time)
Complete analysis of both codebases:
- ✅ Analyzed TypeScript structure at `/mnt/cacho/storage/github/ana`
- ✅ Analyzed Python structure at `/home/blah/poc/aicoder/v3`
- ✅ Created comprehensive `port-progress.json` feature map
- ✅ Updated `AGENTS.md` to remove outdated progress info

### 2. Feature List Management
Each component is broken down into granular sub-features in `port-progress.json`:
```json
{
  "component": "core.aicoder",
  "feature": "runNonInteractive() method",
  "passes": false,
  "notes": "Implementation in progress"
}
```

### 3. Incremental Progress Rule
**ONE sub-feature at a time. No exceptions.**
- Pick the highest priority uncompleted feature
- Implement it completely
- Test it matches TS behavior exactly
- Update progress JSON (mark as `passes: true`)
- Only then move to the next feature

### 4. Testing Strategy
Every feature must:
- Match TypeScript method signatures exactly
- Handle the same edge cases as TS version
- Pass integration tests with surrounding code
- Not break existing functionality

### 5. Session Flow
Each coding session follows this pattern:

#### 5.1 Get Bearings (Every Session Start)
1. Read `port-progress.json` to understand current state
2. Read git/fossil history to see recent work
3. Pick the highest priority uncompleted feature
4. Verify related tests still pass

#### 5.2 Implementation
1. Read the TypeScript source implementation
2. Translate directly to Python (no "improvements")
3. Test the specific feature in isolation
4. Test integration with dependent code
5. Update progress tracking

#### 5.3 Clean State
1. Verify all existing tests still pass
2. Run basic smoke tests
3. Update `port-progress.json` with new status
4. Mark feature as `passes: true` only after thorough verification

## Failure Modes and Solutions

| Failure Mode | Solution |
|--------------|----------|
| Trying to implement too much at once | ONE sub-feature at a time rule |
| Marking features complete without testing | Only mark `passes: true` after verification |
| Losing track between sessions | `port-progress.json` provides context |
| Overengineering improvements | Translate TS exactly, no enhancements |
| Breaking existing functionality | Run tests before marking complete |

## Priority System

Priority 1 (Critical Path):
- Core application flow (aicoder.py main methods)
- Entry points and orchestration

Priority 2 (Core Features):
- Streaming and delta handling
- Tool execution and validation
- Error handling patterns

Priority 3 (Supporting):
- Utility functions
- Type definitions
- Documentation

## Verification Checklist

Before marking any feature as `passes: true`:

- [ ] Method signature matches TS exactly
- [ ] All TS edge cases handled
- [ ] Integration with dependent code works
- [ ] Existing tests still pass
- [ ] No regression in functionality
- [ ] Error handling matches TS behavior

## Current Status

**Phase**: Implementation
**Next Task**: Implement `runNonInteractive()` method with exact TS behavior
**Reference**: `/mnt/cacho/storage/github/ana/src/core/aicoder.ts` lines 342-370

## Commit Strategy

Commits happen only at safe, tested states:
- Each completed sub-feature can be committed
- Must pass all verification checks
- Commit message follows pattern: `feat(core): implement runNonInteractive() method`

## Success Metrics

- All components marked as `passes: true` in progress JSON
- Python behavior identical to TypeScript in all scenarios
- No overengineering or unnecessary complexity
- Clean, maintainable code structure

## Tools Used

- `port-progress.json` - Progress tracking
- `AGENTS.md` - Core documentation (no progress info)
- Fossil for version control
- Direct TS-to-Python translation (no AI hallucinations)

This methodology ensures systematic, verifiable progress without the usual pitfalls of complex porting projects.