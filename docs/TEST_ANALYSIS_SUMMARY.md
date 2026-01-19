# Test Coverage Analysis - Summary & Action Plan

## Executive Summary

**Don't delete all tests.** Instead: **pivot to integration-first testing with pexpect.**

---

## Current State

| Metric | Value | Assessment |
|--------|-------|------------|
| Test files | 72 | Too many |
| Test LOC | 20,058 | 2.2x production code (too high) |
| Test-to-code ratio | 2.2:1 | Should be 1.3:1 |
| Coverage (est.) | 40-50% | Critical paths under-tested |
| Quality | 6/10 | Good tests for wrong things |

## Key Findings

### ✅ What's Working Well

1. **Tool tests** - Comprehensive coverage of read/write/edit/grep
2. **Mock API server** - Clever approach, no API credits burned
3. **Socket server tests** - Good integration testing
4. **Compaction tests** - Complex logic well-tested
5. **Config tests** - Simple and complete

### ❌ What's Not Working

1. **Over-engineering**
   - Test harness too complex (356 lines)
   - Duplicate sandbox tests in every tool file
   - Over-mocked unit tests (test mocks, not code)
   - 6-9 debug scripts in test directory

2. **Uneven coverage**
   - Core orchestration (aicoder.py) - only 8 basic tests
   - Streaming client (502 LOC) - only 84 lines of tests
   - AI processor - minimal dedicated tests
   - No end-to-end workflow tests

3. **Test quality issues**
   - Tests check attributes exist, not behavior
   - "It doesn't crash" testing without assertions
   - Mock interaction testing instead of real behavior

---

## The Pivot: pexpect Integration Tests

### Why pexpect?

Tests the **actual user experience**:
```
User types "hello" → AI processes → Tools execute → Response displayed
```

Not just:
```python
# This tests mock interactions
@patch('everything')
def test_something(self, mock_thing):
    assert mock_thing.called  # Tests nothing real
```

### What I've Created

1. **`tests/integration/tui/test_basic_conversation.py`** (430 lines)
   - Basic conversation flow
   - Tool execution with approval
   - Error recovery
   - Built-in commands
   - Complete write/read workflow

2. **`docs/TEST_REFACTOR_PLAN.md`** (396 lines)
   - Detailed 4-phase plan
   - Specific files to delete/keep
   - Implementation timeline
   - Expected metrics

3. **Updated `pyproject.toml`**
   - Added `pexpect>=4.8.0` to test dependencies

---

## Action Plan

### Phase 1: Quick Cleanup (1-2 hours) ⚡

Delete these debug/verification scripts:
```bash
rm tests/debug_completer.py
rm tests/debug_completer2.py
rm tests/debug_completer3.py
rm tests/debug_completer4.py
rm tests/debug_plugin_load.py
rm tests/debug_register.py
rm tests/fix_verification.py
rm tests/verify_completion.py
rm tests/no_change_approval_test.py
```

**Impact:** -1,500 LOC, cleaner test directory

### Phase 2: Add More pexpect Tests (4-6 hours) 🎯

Create these test files:
```
tests/integration/tui/
├── test_basic_conversation.py     ✓ DONE
├── test_tool_execution.py          TODO
├── test_error_recovery.py         TODO
├── test_commands.py                TODO
└── test_compaction_integration.py TODO
```

Each test should:
- Start aicoder with mock API
- Simulate user input via pexpect
- Verify real file system changes
- Test approval flows
- Verify error messages

**Impact:** +500 LOC, 70% coverage of critical paths

### Phase 3: Simplify Existing Tests (3-4 hours) 🧹

1. **Consolidate sandbox tests**
   - Create `tests/shared/test_sandbox.py`
   - Remove duplicate sandbox tests from tool files
   - Use parametrization

2. **Simplify test harness**
   - Reduce `tests/utils/test_harness.py` complexity
   - Keep only what pexpect tests need

3. **Reduce mock usage**
   - Keep tests that verify real behavior
   - Remove tests that only check attributes exist
   - Delete "it doesn't crash" tests

**Impact:** -2,500 LOC, better signal-to-noise

### Phase 4: Review & Cleanup (1-2 hours) ✅

- Run full test suite
- Update documentation
- Verify coverage metrics
- Clean up any remaining issues

---

## Expected Results

### Before
- 72 test files, 20,058 LOC
- 2.2:1 test-to-code ratio
- 40-50% estimated coverage
- 0 end-to-end tests
- 6-9 debug scripts

### After
- 55 test files, ~12,000 LOC
- 1.3:1 test-to-code ratio
- 60-70% coverage (critical paths)
- 10+ end-to-end tests
- 0 debug scripts

### Quality Improvements

1. **Tests Catch Real Bugs**
   - pexpect tests verify actual user workflows
   - Integration tests with real components
   - Less mocking = more real behavior

2. **Faster Debugging**
   - Clear test failures
   - Real execution context
   - Easier to understand failures

3. **Better Documentation**
   - pexpect tests serve as usage examples
   - Clear test structure
   - Easier for new contributors

4. **Reduced Maintenance**
   - Less test code to maintain
   - Fewer duplicate patterns
   - Clear separation of concerns

---

## What to Keep vs Delete

### ✅ Keep These Tests

| Category | Examples | Why |
|----------|----------|-----|
| Tool unit tests | read_file, write_file, edit_file | Security-critical, edge cases |
| Complex logic | compaction_service | Algorithms need unit tests |
| Integration tests | socket_server, mock_api | Already good |
| Simple utilities | datetime, path, config | Easy to maintain |

### ❌ Delete These Tests

| Category | Examples | Why |
|----------|----------|-----|
| Debug scripts | debug_completer*.py, debug_plugin_load.py | Not tests |
| Verification scripts | fix_verification.py, verify_completion.py | Not tests |
| Duplicate patterns | Sandbox tests in every tool file | Consolidate instead |
| Shallow tests | test_aicoder.py (current version) | Test behavior, not attributes |
| Over-mocked tests | Tests that only mock | Test real behavior |

### 🔄 Simplify These Tests

| Category | Action |
|----------|--------|
| Tool tests | Remove duplicate sandbox tests |
| Test harness | Reduce complexity |
| Core components | Add behavior tests, not just existence checks |
| Mock-heavy tests | Reduce mocking, add integration tests |

---

## Timeline

| Week | Tasks | Hours |
|------|-------|-------|
| 1 | Phase 1: Delete debug scripts | 1-2 |
| 2 | Phase 2: Write pexpect tests | 4-6 |
| 3 | Phase 3: Simplify existing tests | 3-4 |
| 4 | Phase 4: Review & cleanup | 1-2 |

**Total: 9-14 hours**

---

## Next Steps

1. **Install pexpect:**
   ```bash
   pip install pexpect
   ```

2. **Run the first pexpect test:**
   ```bash
   pytest tests/integration/tui/test_basic_conversation.py -v
   ```

3. **Delete debug scripts:**
   ```bash
   # See Phase 1 above
   ```

4. **Write more pexpect tests:**
   - Follow pattern in `test_basic_conversation.py`
   - Focus on critical user workflows
   - Test real behavior, not mocks

5. **Simplify existing tests:**
   - Consolidate sandbox tests
   - Reduce mock usage
   - Keep only valuable tests

---

## Success Criteria

- [ ] All debug scripts removed
- [ ] At least 5 pexpect integration tests passing
- [ ] Existing test suite still passes
- [ ] Test LOC reduced by at least 30%
- [ ] End-to-end coverage of critical user workflows
- [ ] Test execution time under 30 seconds for quick feedback
- [ ] Documentation updated

---

## Documentation Created

1. **`docs/TEST_REFACTOR_PLAN.md`** - Detailed implementation plan
2. **`docs/TEST_ANALYSIS_SUMMARY.md`** - This document
3. **`tests/integration/tui/test_basic_conversation.py`** - Example pexpect tests
4. **`pyproject.toml`** - Updated with pexpect dependency

---

## Final Recommendation

**Don't delete all tests.** You have valuable tests for:
- Tool execution (keep, but simplify)
- Complex logic (compaction, socket server)
- Utilities (datetime, path, config)

**Add pexpect tests** for:
- User workflows
- Tool execution chains
- Error recovery
- TUI interactions

**Remove**:
- Debug scripts
- Duplicate patterns
- Over-mocked tests
- Shallow existence checks

**Result**: Better coverage, fewer tests, higher quality.

---

**Status:** ✅ Analysis complete, first pexpect test written, plan documented
**Next Step:** Run `pytest tests/integration/tui/test_basic_conversation.py -v`
