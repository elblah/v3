"""
compact_strategy.py - Token-aware compaction strategy plugin

Triggers compaction when context reaches threshold, but preserves
configurable amount of context instead of brutal full compaction.

Env vars:
  COMPACT_STRATEGY_THRESHOLD     - Trigger compaction at X% of context size (default: disabled)
  COMPACT_STRATEGY_KEEP_MESSAGES - Keep N newest messages (mutually exclusive with KEEP_PERCENT)
  COMPACT_STRATEGY_KEEP_PERCENT  - Keep N% of tokens from newest messages (mutually exclusive)

Example:
  COMPACT_STRATEGY_THRESHOLD=50 COMPACT_STRATEGY_KEEP_MESSAGES=30 aicoder
  # When context > 50%, compact but keep 30 newest messages

  COMPACT_STRATEGY_THRESHOLD=50 COMPACT_STRATEGY_KEEP_PERCENT=20 aicoder
  # When context > 50%, compact but keep 20% of current tokens
"""

import os
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """Create compact strategy plugin"""
    app = ctx.app

    # Read configuration
    threshold_pct = int(os.environ.get("COMPACT_STRATEGY_THRESHOLD", "0"))
    keep_messages = os.environ.get("COMPACT_STRATEGY_KEEP_MESSAGES")
    keep_percent = os.environ.get("COMPACT_STRATEGY_KEEP_PERCENT")

    if threshold_pct <= 0:
        return {}

    if keep_messages and keep_percent:
        LogUtils.error("[!] compact_strategy: KEEP_MESSAGES and KEEP_PERCENT are mutually exclusive")
        return {}

    # Track last compaction size to avoid re-triggering
    _last_compact_size = 0

    def _on_after_ai_processing(has_tool_calls=None):
        nonlocal _last_compact_size

        stats = app.stats
        current_tokens = stats.current_prompt_size or 0
        max_tokens = Config.context_size()

        if current_tokens == 0:
            return

        # Check if threshold reached
        threshold_tokens = int(max_tokens * (threshold_pct / 100))
        if current_tokens < threshold_tokens:
            return

        # Avoid re-triggering (only compact once per growth cycle)
        if current_tokens <= _last_compact_size:
            return

        _last_compact_size = current_tokens

        # Calculate how many messages to keep
        if keep_messages:
            n = -int(keep_messages)
            msg_count = app.message_history.get_message_count()
            LogUtils.print(f"[compact_strategy] Context {current_tokens}/{max_tokens} ({100*current_tokens/max_tokens:.0f}%) - keeping {keep_messages} msgs, compacting {max(0, msg_count - int(keep_messages))}")
            app.message_history.force_compact_messages(n)
        elif keep_percent:
            target_tokens = int(max_tokens * (int(keep_percent) / 100))
            messages = app.message_history.messages

            # Iterate from newest backwards, sum cached tokens
            kept = 0
            count = 0
            for msg in reversed(messages):
                if msg.get("role") == "system":
                    continue
                # Use cached token count
                from aicoder.core.token_estimator import _message_cache
                tokens = _message_cache.get(id(msg), 0)
                if kept + tokens > target_tokens:
                    break
                kept += tokens
                count += 1

            n = -count
            LogUtils.print(f"[compact_strategy] Context {current_tokens}/{max_tokens} ({100*current_tokens/max_tokens:.0f}%) - keeping {keep_percent}% ({target_tokens} tokens, ~{count} msgs)")
            app.message_history.force_compact_messages(n)
        else:
            LogUtils.warn("[!] compact_strategy: No KEEP_MESSAGES or KEEP_PERCENT set")
            return

    # Register hook
    ctx.register_hook("after_ai_processing", _on_after_ai_processing)

    if Config.debug():
        LogUtils.print("[+] compact_strategy plugin loaded")
        LogUtils.print(f"  - Threshold: {threshold_pct}% of {Config.context_size()} tokens")
        if keep_messages:
            LogUtils.print(f"  - Keep messages: {keep_messages}")
        elif keep_percent:
            LogUtils.print(f"  - Keep percent: {keep_percent}%")
