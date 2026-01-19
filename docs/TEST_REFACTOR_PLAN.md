# Test Refactoring Plan

## Executive Summary

**Current State:**
- 72 test files, ~20,000 LOC
- Test-to-code ratio: 2.2:1 (too high)
- Coverage: ~40-50% (estimated)
- Quality: 6/10

**Target State:**
- ~55 test files, ~12,000 LOC
- Test-to-code ratio: 1.3:1 (reasonable)
- Coverage: 60-70% (critical paths)
- Quality: 8/10

**Strategy:** Keep valuable unit tests, add integration tests, remove over-engineering

---

## Phase 1: Cleanup (Quick Wins - 1-2 hours)

### Files to Delete (or move to `scripts/debug/`)

```
tests/debug_completer.py
tests/debug_completer2.py
tests/debug_completer3.py
tests/debug_completer4.py
tests/debug_plugin_load.py
tests/debug_register.py
tests/fix_verification.py
tests/verify_completion.py
tests/no_change_approval_test.py
```

**Rationale:** These are not tests - they're debugging scripts that ended up in the test directory.

### Impact
- LOC reduction: ~1,500 lines
- Test files: 72 → 63
- Zero risk - no actual test code removed

---

## Phase 2: Add pexpect Tests (High Value - 4-6 hours)

### New Directory Structure

```
tests/integration/tui/
├── test_basic_conversation.py     (430 LOC - DONE ✓)
├── test_tool_execution.py          (TODO)
├── test_error_recovery.py         (TODO)
├── test_commands.py                (TODO)
└── test_compaction_integration.py (TODO)
```

### Test Coverage Goals

Each pexpect test should verify:
1. Real TUI interaction (prompts, inputs, outputs)
2. Tool execution with approval flow
3. Error handling and recovery
4. End-to-end workflows
5. Built-in commands

### Example Test Pattern

```python
def test_workflow(mock_server, aicoder_env, tmp_path):
    """Test complete workflow from user input to file change."""
    # 1. Set up mock API responses
    mock_server.set_response("user input", ...)

    # 2. Start aicoder with pexpect
    child = pexpect.spawn("python -m aicoder", ...)

    # 3. Simulate user interaction
    child.expect(r"You>")
    child.sendline("user input")
    child.expect(r"tool.*approval")
    child.sendline("y")

    # 4. Verify final state
    child.expect(r"success message")
    assert expected_file_content == actual_file_content
```

### Dependencies Added

```toml
[project.optional-dependencies]
test = [
    "pytest>=7.0.0",
    "pytest-mock>=3.10.0",
    "pexpect>=4.8.0",  # NEW
]
```

### Impact
- LOC added: ~500 lines
- Critical path coverage: 40% → 70%
- Real user behavior testing: 0% → 60%

---

## Phase 3: Simplify Existing Tests (Medium Value - 3-4 hours)

### 3.1 Consolidate Sandbox Tests

**Problem:** Sandbox tests duplicated in every tool test file (~100 lines each)

**Solution:** Create shared sandbox tests

```python
# tests/shared/test_sandbox.py

@pytest.mark.parametrize("module_path", [
    "aicoder.tools.internal.read_file",
    "aicoder.tools.internal.write_file",
    "aicoder.tools.internal.edit_file",
])
class TestSandboxBehavior:
    """Test sandbox enforcement across all tools."""
    def test_sandbox_disabled(self, module_path):
        ...
    def test_path_within_current_dir(self, module_path):
        ...
    def test_path_outside_current_dir(self, module_path):
        ...
```

**Impact:**
- LOC reduction: ~400 lines (4 files × 100 lines)
- Better maintainability (one place to update)

### 3.2 Simplify Test Harness

**Current:** `tests/utils/test_harness.py` - 356 lines

**Issues:**
- Complex fixture infrastructure
- Helper classes with abstractions
- Over-engineered for YAGNI principles

**Action:**
- Remove unnecessary abstractions
- Simplify fixture setup
- Keep only what's needed for pexpect tests

**Impact:**
- LOC reduction: ~200 lines
- Easier to understand for new contributors

### 3.3 Reduce Mock Usage

**Problem:** Many unit tests mock everything and test mock interactions

**Example of over-mocking:**
```python
@patch('aicoder.tools.internal.write_file.Config')
@patch('aicoder.tools.internal.write_file._check_sandbox')
@patch('aicoder.tools.internal.write_file.file_write')
def test_write_something(self, mock_write, mock_sandbox, mock_config):
    # Tests mock interactions, not real behavior
```

**Solution:**
- Keep only tests that verify actual behavior
- Remove tests that just check attributes exist
- Prefer integration tests for complex behavior
- Keep unit tests for pure functions and edge cases

**Impact:**
- LOC reduction: ~2,000 lines
- Better signal-to-noise ratio

---

## Phase 4: Keep Valuable Tests (No Changes)

### Keep These Tests As-Is

| Test File | LOC | Reason |
|-----------|-----|--------|
| `test_compaction_service.py` | 342 | Complex logic, good unit tests |
| `test_socket_server_unit.py` | 1,037 | Complex component, comprehensive |
| `test_config.py` | 485 | Simple, complete coverage |
| `test_datetime_utils.py` | 68 | Pure functions, good tests |
| `test_path_utils.py` | 58 | Security-critical, good tests |
| `test_http_utils.py` | ~100 | Network utilities |
| `test_jsonl_utils.py` | 103 | Data handling |
| Integration tests | ~500 | Already good |

### Simplified Tool Tests

Keep tool tests but reduce duplication:
- Remove duplicate sandbox tests (moved to shared)
- Reduce mock usage
- Keep edge case tests
- Keep error handling tests

---

## Expected Results

### Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Test files | 72 | 55 | -17 |
| Test LOC | 20,058 | 12,000 | -40% |
| Test-to-code ratio | 2.2:1 | 1.3:1 | -41% |
| Critical path coverage | 40% | 70% | +75% |
| End-to-end tests | 0 | 10 | +10 |
| Integration tests | 5 | 15 | +200% |
| Debug scripts in tests | 9 | 0 | -100% |

### Quality Improvements

1. **Tests Catch Real Bugs:** pexpect tests verify actual user workflows
2. **Faster Debugging:** Clear test failures with real behavior
3. **Easier Onboarding:** Simple test structure
4. **Better Documentation:** pexpect tests serve as usage examples
5. **Reduced Maintenance:** Less test code to maintain

### Time Investment

- Phase 1 (Cleanup): 1-2 hours
- Phase 2 (pexpect tests): 4-6 hours
- Phase 3 (Simplify): 3-4 hours
- Phase 4 (Review): 1-2 hours

**Total: 9-14 hours**

### Risk Assessment

| Action | Risk | Mitigation |
|--------|------|------------|
| Delete debug scripts | Low | These are not tests, just move to scripts/ if needed |
| Add pexpect tests | Low | Don't affect existing tests, just add new coverage |
| Simplify unit tests | Medium | Run existing test suite to ensure no regressions |
| Consolidate sandbox tests | Low | Keep same test coverage, just reorganized |

---

## Implementation Order

1. **Week 1:**
   - Phase 1: Delete debug scripts (1-2 hours)
   - Add pexpect dependency (5 minutes)
   - Create `tests/integration/tui/` directory

2. **Week 2:**
   - Phase 2: Write 5 pexpect tests (4-6 hours)
   - Run and verify all pass

3. **Week 3:**
   - Phase 3a: Consolidate sandbox tests (1 hour)
   - Phase 3b: Simplify test harness (1 hour)
   - Phase 3c: Reduce mock usage in tool tests (2 hours)

4. **Week 4:**
   - Review and cleanup (1-2 hours)
   - Update documentation
   - Ensure all tests pass

---

## Test Coverage Targets After Refactor

### High Coverage (>80%)
- Tool execution (read, write, edit, etc.)
- Sandbox enforcement
- Path utilities
- Config system

### Medium Coverage (60-80%)
- Socket server
- Message history
- Plugin system
- Compaction service

### Good Coverage (>50%)
- Streaming client (with pexpect tests)
- AI processor (with pexpect tests)
- Core orchestration (with pexpect tests)

---

## Maintenance Guidelines

### When to Write Unit Tests

- **Write:** Pure functions with complex logic
- **Write:** Edge cases and error handling
- **Write:** Security-critical code (sandbox, path validation)
- **Write:** Algorithm implementations

### When to Write Integration Tests

- **Write:** User-facing workflows
- **Write:** Tool execution chains
- **Write:** Error recovery scenarios
- **Write:** Built-in commands

### When to Write pexpect Tests

- **Write:** TUI interactions
- **Write:** Complete user sessions
- **Write:** Approval flows
- **Write:** Multi-turn conversations

### When NOT to Write Tests

- **Don't:** Test private methods directly
- **Don't:** Test mock interactions (test real behavior)
- **Don't:** Write tests that only check attributes exist
- **Don't:** Write tests that don't fail if code changes

---

## Success Criteria

1. ✅ All debug scripts removed or relocated
2. ✅ At least 5 pexpect integration tests passing
3. ✅ Existing test suite still passes
4. ✅ Test LOC reduced by at least 30%
5. ✅ End-to-end coverage of critical user workflows
6. ✅ Documentation updated with new test structure
7. ✅ Test execution time under 30 seconds for quick feedback

---

## Open Questions

1. **Should we keep any tool unit tests?** Yes, but simplified versions without duplicate sandbox tests
2. **Should we write pexpect tests for every feature?** No, focus on critical user workflows
3. **Should we require pexpect for all environments?** Make it optional, skip gracefully if not available
4. **Should we keep the complex test harness?** Simplify it to minimum needed for pexpect tests

---

## Appendix: Example Test Structure After Refactor

```
tests/
├── integration/
│   ├── tui/
│   │   ├── test_basic_conversation.py      ✓ NEW
│   │   ├── test_tool_execution.py          TODO
│   │   ├── test_error_recovery.py         TODO
│   │   ├── test_commands.py                TODO
│   │   └── test_compaction_integration.py TODO
│   ├── mock_server.py                      KEEP
│   ├── test_compaction.py                  KEEP
│   └── test_run_shell_command.py           KEEP
│
├── unit/
│   ├── test_compaction_service.py          KEEP
│   ├── test_message_history.py             SIMPLIFY
│   ├── test_plugin_system.py               SIMPLIFY
│   └── test_socket_server.py              SIMPLIFY
│
├── tools/
│   ├── test_read_file.py                  SIMPLIFY
│   ├── test_write_file.py                 SIMPLIFY
│   ├── test_edit_file.py                  SIMPLIFY
│   ├── test_grep.py                       SIMPLIFY
│   └── test_list_directory.py            SIMPLIFY
│
├── shared/
│   └── test_sandbox.py                    NEW (consolidated)
│
├── utils/
│   └── test_harness.py                    SIMPLIFY
│
├── test_aicoder.py                        SIMPLIFY
├── test_config.py                         KEEP
├── test_datetime_utils.py                 KEEP
└── test_path_utils.py                     KEEP

# DELETED:
# tests/debug_completer*.py
# tests/debug_plugin_load.py
# tests/debug_register.py
# tests/fix_verification.py
# tests/verify_completion.py
# tests/no_change_approval_test.py
```

---

**Status:** Plan created, first pexpect test written
**Next Step:** Begin Phase 1 cleanup
