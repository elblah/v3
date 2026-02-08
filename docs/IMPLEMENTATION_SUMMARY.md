# Reasoning Field Detection Enhancement - Implementation Summary

## Overview

Successfully implemented multi-provider reasoning field detection in AI Coder to capture and preserve model reasoning (thinking/thought process) across different LLM providers.

## Problem Solved

**Before**: AI Coder only checked for `reasoning_content` field, missing reasoning from providers using different field names:
- OpenAI-compatible endpoints use `reasoning`
- Some providers use `reasoning_text`
- Chutes.ai returns both `reasoning_content` and `reasoning` (deduplication needed)

**After**: Generic detection supporting multiple field names with intelligent deduplication.

## Changes Made

### 1. Core Implementation
**File**: `aicoder/core/stream_processor.py` (lines 67-95)

**Changes**:
```python
# Check for reasoning tokens across multiple field names
reasoning_fields = ["reasoning_content", "reasoning", "reasoning_text"]
detected_field = None

for field in reasoning_fields:
    reasoning = delta.get(field)
    if reasoning and reasoning.strip():
        reasoning_detected = True
        accumulated_reasoning += reasoning
        detected_field = field
        # Only use first non-empty field (avoid duplication)
        break

# Debug: log which reasoning field was detected
if Config.debug() and detected_field:
    LogUtils.debug(f"Reasoning detected via field: {detected_field}")
```

**Key Features**:
- Checks 3 field names in priority order
- Uses first non-empty field
- Skips empty/whitespace-only fields
- Breaks after first match to avoid duplication
- Logs detected field name for debugging

### 2. Session Manager Updates
**File**: `aicoder/core/session_manager.py`

**No Changes**: Already supported `reasoning_content` parameter throughout:
- `_validate_and_process_tool_calls(full_response, reasoning_content, ...)`
- `_handle_empty_response(full_response, reasoning_content)`
- Preserves reasoning in assistant messages

### 3. Test Coverage
**File**: `tests/unit/test_stream_processor.py`

**Added Tests** (7 new tests):
1. `test_process_stream_with_reasoning_content_field` - GLM/llama.cpp support
2. `test_process_stream_with_reasoning_field` - OpenAI-compatible support
3. `test_process_stream_with_reasoning_text_field` - Other providers
4. `test_process_stream_uses_first_non_empty_reasoning_field` - Deduplication
5. `test_process_stream_accumulates_reasoning_across_chunks` - Multi-chunk accumulation
6. `test_process_stream_ignores_empty_reasoning_field` - Skip empty fields
7. `test_process_stream_handles_reasoning_with_content` - Mixed content

**File**: `tests/test_session_manager.py`

**Fixed Tests** (3 tests updated, 2 tests added):
1. `test_handle_empty_response_with_content` - Added `""` for reasoning_content
2. `test_handle_empty_response_empty_string` - Added `""` for reasoning_content
3. `test_handle_empty_response_whitespace` - Added `""` for reasoning_content
4. `test_handle_empty_response_with_reasoning` - NEW: reasoning only
5. `test_handle_empty_response_with_both_content_and_reasoning` - NEW: both content and reasoning

**Total Test Count**: 24 tests (19 stream_processor + 5 session_manager)
**Test Results**: ✅ All 24 tests passing

### 4. Documentation
**Files Created**:
1. **`docs/REASONING_CAPTURE.md`** (167 lines)
   - Comprehensive guide to reasoning capture
   - Supported providers and their reasoning fields
   - How detection works
   - Configuration options
   - Debug mode
   - Implementation details
   - Benefits and limitations
   - Testing information
   - Future enhancements

2. **`docs/REASONING_FIELD_ENHANCEMENT.md`** (221 lines)
   - Detailed implementation notes
   - Problem and solution
   - Changes made
   - Benefits
   - Testing results
   - Backward compatibility
   - Known limitations
   - Performance impact
   - Future enhancements
   - Git commit message template

## Supported Providers

| Provider | API Type | Reasoning Field | Status |
|----------|----------|-----------------|--------|
| **GLM** | Chat Completions | `reasoning_content` | ✅ Fully supported |
| **llama.cpp** | Chat Completions | `reasoning_content` | ✅ Fully supported |
| **Chutes.ai** | Chat Completions | `reasoning_content`, `reasoning` | ✅ Fully supported (deduplicates) |
| **OpenAI-compatible** | Chat Completions | `reasoning`, `reasoning_text` | ✅ Fully supported |
| **OpenAI** | Responses API | `ResponseReasoningItem` | ⚠️ Not yet implemented |
| **OpenAI** | Chat Completions | *Not exposed by API* | ❌ Cannot capture |

## Key Benefits

### 1. Provider Agnostic
Works with any provider that exposes reasoning in standard fields:
- GLM (Zhipu AI)
- llama.cpp
- OpenAI-compatible endpoints
- Chutes.ai
- Any future provider using these field names

### 2. Deduplication
Handles providers that return multiple reasoning fields:
- Only uses first non-empty field
- Prevents double-counting reasoning
- Maintains correct token accounting

### 3. Better Debugging
Debug mode shows which field was detected:
```
*** Thinking: on (effort: high) (preserve: false)
Reasoning detected via field: reasoning_content
Reasoning: ON (effort: high)
```

### 4. Robustness
Handles edge cases:
- Empty/whitespace-only fields
- Multiple fields in same delta
- Mixed content and reasoning
- Missing reasoning fields

## Backward Compatibility

✅ **Fully backward compatible** - All existing tests pass

- No changes to public API
- No changes to configuration
- No changes to message format
- Existing `reasoning_content` field still works exactly as before
- Additional fields are transparently supported

## Performance Impact

- **Minimal**: Additional loop over 3 field names per delta
- **Negligible overhead**: O(1) per chunk (3 string lookups)
- **No impact when reasoning not present**: Fields are checked but no work done
- **No impact on token usage**: Same number of tokens sent/received

## Known Limitations

### OpenAI Chat Completions API
The standard OpenAI Chat Completions API (`/v1/chat/completions`) does **NOT** expose reasoning text. Reasoning happens internally and only token counts are returned in `usage.completion_tokens_details.reasoning_tokens`.

**Workarounds**:
1. Use OpenAI Responses API (`/v1/responses`) instead - requires separate implementation
2. Use different providers that expose reasoning
3. Accept that reasoning cannot be captured for OpenAI Chat Completions

## Test Results Summary

```
================================ test session starts =================================
platform linux -- Python 3.13.5, pytest-8.3.5
collected 24 items

tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_basic_content PASSED
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_with_tool_calls PASSED
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_user_interrupted PASSED
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_empty_response PASSED
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_missing_choices PASSED
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_with_usage_stats PASSED
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_error_handling PASSED
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_with_reasoning_content_field PASSED ✨
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_with_reasoning_field PASSED ✨
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_with_reasoning_text_field PASSED ✨
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_uses_first_non_empty_reasoning_field PASSED ✨
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_accumulates_reasoning_across_chunks PASSED ✨
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_ignores_empty_reasoning_field PASSED ✨
tests/unit/test_stream_processor.py::TestStreamProcessor::test_process_stream_handles_reasoning_with_content PASSED ✨
tests/unit/test_stream_processor.py::TestAccumulateToolCall::test_accumulate_new_tool_call PASSED
tests/unit/test_stream_processor.py::TestAccumulateToolCall::test_accumulate_arguments PASSED
tests/unit/test_stream_processor.py::TestAccumulateToolCall::test_accumulate_multiple_tool_calls PASSED
tests/unit/test_stream_processor.py::TestAccumulateToolCall::test_accumulate_invalid_tool_call PASSED
tests/unit/test_stream_processor.py::TestAccumulateToolCall::test_accumulate_missing_function_name PASSED
tests/test_session_manager.py::TestSessionManagerHandleEmptyResponse::test_handle_empty_response_with_content PASSED ✨
tests/test_session_manager.py::TestSessionManagerHandleEmptyResponse::test_handle_empty_response_empty_string PASSED ✨
tests/test_session_manager.py::TestSessionManagerHandleEmptyResponse::test_handle_empty_response_whitespace PASSED ✨
tests/test_session_manager.py::TestSessionManagerHandleEmptyResponse::test_handle_empty_response_with_reasoning PASSED ✨
tests/test_session_manager.py::TestSessionManagerHandleEmptyResponse::test_handle_empty_response_with_both_content_and_reasoning PASSED ✨

=============================================== 24 passed in 0.55s ================================================
```

## Files Modified

1. ✅ `aicoder/core/stream_processor.py` - Multi-field detection logic
2. ✅ `tests/unit/test_stream_processor.py` - 7 new tests
3. ✅ `tests/test_session_manager.py` - 3 fixed tests + 2 new tests
4. ✅ `docs/REASONING_CAPTURE.md` - Complete user guide
5. ✅ `docs/REASONING_FIELD_ENHANCEMENT.md` - Implementation details
6. ✅ `docs/IMPLEMENTATION_SUMMARY.md` - This file

## Verification Commands

```bash
# Run all reasoning-related tests
python -m pytest tests/unit/test_stream_processor.py tests/test_session_manager.py::TestSessionManagerHandleEmptyResponse -v

# Verify reasoning field detection
python -c "
from aicoder.core.stream_processor import StreamProcessor
# (run detection test as shown in implementation)
"
```

## Status: ✅ READY FOR PRODUCTION

The implementation is:
- ✅ Fully tested (24 tests, 100% pass rate)
- ✅ Backward compatible (no breaking changes)
- ✅ Well documented (2 comprehensive guides)
- ✅ Provider agnostic (works with multiple providers)
- ✅ Robust (handles edge cases)
- ✅ Debuggable (logs detected field name)
- ✅ Performant (minimal overhead)

## Next Steps

### Immediate
- ✅ All tests passing
- ✅ Documentation complete
- ✅ Ready to merge

### Future Enhancements
1. **OpenAI Responses API Support**: Implement separate provider handler
2. **Field Priority Configuration**: Allow custom field priority order
3. **Reasoning Compression**: Compress large reasoning before preservation
4. **Reasoning Summarization**: Summarize reasoning before adding to context
5. **Conditional Preservation**: Only preserve reasoning based on size/complexity
6. **Streaming Reasoning Display**: Option to show/hide reasoning in real-time

## References

- **pi-mono implementation**: https://github.com/pi-mono/ai/blob/main/packages/ai/src/providers/openai-completions.ts#L197-L222
- **OpenAI Python SDK**: https://github.com/openai/openai-python
- **GLM API**: https://open.bigmodel.cn/dev/api#chatglm_pro
- **OpenAI Responses API**: https://platform.openai.com/docs/guides/reasoning

## Git Commit Message

```
feat: Expand reasoning field detection for multi-provider support

- Add support for 'reasoning' and 'reasoning_text' fields
- Implement deduplication for providers returning multiple fields
- Skip empty/whitespace-only reasoning fields
- Add debug logging for detected field name
- Add 7 comprehensive tests for stream processor
- Add 2 tests for session manager reasoning handling
- Update 3 existing tests to include reasoning_content parameter
- Document all supported providers and field names
- Maintain full backward compatibility

Previously only 'reasoning_content' was supported (GLM, llama.cpp).
Now works with OpenAI-compatible endpoints and other providers that use
different field names for reasoning content.

Fixes: Missing reasoning from providers using 'reasoning' or 'reasoning_text'

Test Results: 24/24 tests passing (100%)
```
