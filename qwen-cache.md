# Qwen Cache Control Implementation

## Overview
Qwen3.6+ models require explicit `cache_control` tags for prompt caching. Without proper implementation, quota is consumed ~10x faster.

## Key Findings

### Qwen Request Format (sample-qwen.json)
- System message: sent as array with `type: "text"` and `cache_control: {type: "ephemeral"}`
- Last 2-3 messages: also tagged with `cache_control: {type: "ephemeral"}`
- Content uses structured format with `type: "text"` and `type: "thinking"` blocks

### Example Structure
```json
{
  "model": "qwen3.6-plus-free",
  "system": [
    {
      "type": "text",
      "text": "You are opencode...",
      "cache_control": {"type": "ephemeral"}
    }
  ],
  "messages": [
    {"role": "assistant", "content": [{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}]},
    {"role": "user", "content": [{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}]}
  ]
}
```

## Current aicoder Implementation
- streaming_client.py uses standard OpenAI format with `{"role": "system", "content": "..."}` NOT array format
- No `cache_control` tags currently applied
- Messages formatted as plain strings, not structured content blocks

## OpenCode Implementation (transform.ts:340-390)
OpenCode applies cache_control to:
- System messages (first 2)
- Last 2 non-system messages

Provider-specific cache options:
```javascript
const providerOptions = {
  anthropic: { cacheControl: { type: "ephemeral" } },
  openrouter: { cacheControl: { type: "ephemeral" } },
  bedrock: { cachePoint: { type: "default" } },
  openaiCompatible: { cache_control: { type: "ephemeral" } },
  copilot: { copilot_cache_control: { type: "ephemeral" } },
  alibaba: { cacheControl: { type: "ephemeral" } },
}
```

ApplyCaching is called for: anthropic, google-vertex-anthropic, alibaba providers

## Qwen-specific format in sample-qwen.json
- System as array: `{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}`
- Last 2-3 messages also get cache_control on the last content block
- Content uses `{"type": "text", ...}` and `{"type": "thinking", ...}` blocks

## Hermes Demo Results (opencode_cache_demo.sh)
Demonstrates the problem clearly:

**WITH cache_control:** ~10-15 input_tokens (cached)
**WITHOUT cache_control:** ~40-50 input_tokens (billed fresh)

The format they recommend:
```json
{
  "messages": [
    {"role": "system", "content": [{"type": "text", "text": "...", "cache_control": {"type": "ephemeral", "ttl": "5m"}}]},
    {"role": "user", "content": [{"type": "text", "text": "...", "cache_control": {"type": "ephemeral", "ttl": "5m"}}]}
  ]
}
```

Note: Uses `ttl: "5m"` (5 minute TTL) in addition to `type: "ephemeral"`

## Implementation Status

### Done
1. **streaming_client.py:280**: calls `transform_request` hook
2. **anthropic_client.py**: calls `transform_request` hook before return
3. **plugins/alibaba_cache.py**: Created - transforms JSON for Alibaba/Qwen cache format when `AICODER_ALIBABA_CACHE=1`

2. **plugins/alibaba_cache.py**: Created - transforms JSON for Alibaba/Qwen cache format when `AICODER_ALIBABA_CACHE=1`

### Usage
```bash
export AICODER_TRANSFORM_REQUEST=alibaba
aicoder
```

### What the plugin does
- System messages (first 2): `{"role": "system", "content": [{"type": "text", "text": "...", "cache_control": {"type": "ephemeral", "ttl": "5m"}}]}`
- Last 2 non-system messages: same cache_control on last content block

## Investigation Results
- /mnt/gh/opencode: Found in packages/opencode/src/provider/transform.ts (lines 340-460)
- /mnt/gh/hermes-agent: Found opencode_cache_demo.sh with working implementation