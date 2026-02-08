# Reasoning Capture in AI Coder

## Overview

AI Coder supports capturing and preserving model reasoning (thinking/thought process) across conversation turns to maintain context and improve multi-turn coding workflows.

## Supported Providers and APIs

### Providers That Support Reasoning Capture

| Provider | API Type | Reasoning Field | Status |
|----------|----------|-----------------|--------|
| **GLM** | Chat Completions | `reasoning_content` | ✅ Fully supported |
| **llama.cpp** | Chat Completions | `reasoning_content` | ✅ Fully supported |
| **Chutes.ai** | Chat Completions | `reasoning_content`, `reasoning` | ✅ Fully supported (deduplicates) |
| **OpenAI-compatible** | Chat Completions | `reasoning`, `reasoning_text` | ✅ Fully supported |
| **OpenAI** | Responses API | `ResponseReasoningItem` | ⚠️ Not yet implemented |
| **OpenAI** | Chat Completions | *Not exposed by API* | ❌ Cannot capture |

### OpenAI Chat Completions API Limitation

**Important**: The standard OpenAI Chat Completions API (`/v1/chat/completions`) does **NOT** expose reasoning text in the streaming response. Reasoning happens internally and only token counts are returned in `usage.completion_tokens_details.reasoning_tokens`.

To capture OpenAI reasoning, you would need to:
1. Switch to the OpenAI Responses API (`/v1/responses`)
2. Or use a different provider that exposes reasoning

## How It Works

### 1. Detection

AI Coder checks multiple field names to detect reasoning content across different providers:

```python
reasoning_fields = ["reasoning_content", "reasoning", "reasoning_text"]
```

For each streaming chunk, it:
1. Checks each field in order
2. Uses the **first non-empty** field found
3. Accumulates reasoning across multiple chunks
4. Avoids duplication (e.g., when provider returns both `reasoning_content` and `reasoning`)

### 2. Preservation

When reasoning is detected and preserved:
- The full reasoning text is stored in `assistant_message["reasoning_content"]`
- This is added to the message history for subsequent turns
- Helps maintain context across multi-turn conversations

### 3. Configuration

Control reasoning preservation with environment variables:

```bash
# Enable thinking mode
THINKING=on

# Set reasoning effort level (for supported models)
REASONING_EFFORT=high  # low|medium|high|xhigh

# Control whether to preserve reasoning across turns
# Default: false (preserve reasoning)
CLEAR_THINKING=true  # Clear reasoning after each turn
```

### Commands

```bash
# View current reasoning effort
/thinking effort

# Set reasoning effort level
/thinking effort high

# View preservation status
/thinking clear

# Set preservation behavior
/thinking clear true   # Clear reasoning after each turn
/thinking clear false  # Preserve reasoning (default)
```

## Debug Mode

When `DEBUG=1`, AI Coder logs reasoning detection:

```
*** Thinking: on (effort: high) (preserve: false)
Reasoning detected via field: reasoning_content
Reasoning: ON (effort: high)
```

## Implementation Details

### Field Detection Logic

```python
# From aicoder/core/stream_processor.py
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

### Message History Storage

```python
# From aicoder/core/session_manager.py
# Add reasoning_content if present (preserved thinking)
if reasoning_content:
    assistant_message["reasoning_content"] = reasoning_content

self.message_history.add_assistant_message(assistant_message)
```

## Testing

The reasoning capture functionality is fully tested in:
- `tests/unit/test_stream_processor.py` - 19 tests including:
  - `test_process_stream_with_reasoning_content_field`
  - `test_process_stream_with_reasoning_field`
  - `test_process_stream_with_reasoning_text_field`
  - `test_process_stream_uses_first_non_empty_reasoning_field`
  - `test_process_stream_accumulates_reasoning_across_chunks`
  - `test_process_stream_ignores_empty_reasoning_field`
  - `test_process_stream_handles_reasoning_with_content`

## Benefits

1. **Context Preservation**: Maintains reasoning context across turns
2. **Better Multi-turn Coding**: Model can recall its thought process
3. **Debugging**: You can review model reasoning when troubleshooting
4. **Provider Agnostic**: Works with multiple providers automatically
5. **Deduplication**: Handles providers that return multiple reasoning fields

## Known Limitations

1. **OpenAI Chat Completions**: Cannot capture reasoning (API limitation)
2. **Token Cost**: Preserving reasoning increases context window usage
3. **Memory Usage**: Large reasoning content uses more memory
4. **API Compatibility**: Some providers may not respect reasoning content in context

## Future Enhancements

- [ ] Switch to OpenAI Responses API for OpenAI models to capture reasoning
- [ ] Add compression for large reasoning content
- [ ] Implement reasoning summarization before preservation
- [ ] Add UI controls for reasoning visibility
- [ ] Support reasoning content in compaction summaries

## References

- [pi-mono provider implementations](https://github.com/pi-mono/ai/blob/main/packages/ai/src/providers/openai-completions.ts)
- [OpenAI Python SDK reasoning types](https://github.com/openai/openai-python)
- [OpenAI Responses API docs](https://platform.openai.com/docs/guides/reasoning)
