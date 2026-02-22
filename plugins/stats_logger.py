"""
Stats Logger Plugin

Logs each AI API request to .aicoder/stats.log for later analysis.
Format: <timestamp>|<base_url>|<model>|<prompt_tokens>|<completion_tokens>|<elapsed_seconds>
"""

import os
from datetime import datetime
from aicoder.core.config import Config
from aicoder.core.token_estimator import _estimate_weighted_tokens


def create_plugin(ctx):
    """Plugin entry point"""

    # Track last token counts to calculate deltas
    last_prompt_tokens = 0
    last_completion_tokens = 0
    # Store estimated completion tokens from message content
    estimated_completion_tokens = 0

    def _on_assistant_message(assistant_message):
        """Hook after assistant message is added - estimate completion tokens if needed"""
        nonlocal estimated_completion_tokens

        stats = ctx.app.stats
        if not stats:
            return

        # If API didn't return completion tokens, estimate from message content
        if stats.completion_tokens == 0 and assistant_message.get("content"):
            content = assistant_message["content"]
            # Use proper token estimation
            estimated_completion_tokens = _estimate_weighted_tokens(content)

    def _log_api_request(has_tool_calls: bool):
        """Log API request to stats.log"""
        nonlocal last_prompt_tokens, last_completion_tokens, estimated_completion_tokens

        stats = ctx.app.stats

        if not stats:
            return

        # Calculate delta from last request
        prompt_tokens = stats.prompt_tokens - last_prompt_tokens
        completion_tokens = stats.completion_tokens - last_completion_tokens

        # Update last counts for next request
        last_prompt_tokens = stats.prompt_tokens
        last_completion_tokens = stats.completion_tokens

        # If prompt delta is zero, use current prompt size (already properly estimated)
        if prompt_tokens == 0 and stats.current_prompt_size > 0:
            prompt_tokens = max(1, stats.current_prompt_size)

        # If completion delta is zero but we have an estimate, use it
        if completion_tokens == 0 and estimated_completion_tokens > 0:
            completion_tokens = estimated_completion_tokens

        # Reset estimate after using it
        estimated_completion_tokens = 0

        # Get model and endpoint from config
        model = Config.model()
        base_url = Config.base_url()

        # Get elapsed time from stats
        elapsed = stats.last_api_time

        # Format timestamp (UTC)
        timestamp = datetime.now().isoformat(timespec='seconds')

        # Format log line
        log_line = f"{timestamp}|{base_url}|{model}|{prompt_tokens}|{completion_tokens}|{elapsed:.2f}\n"

        # Ensure .aicoder dir exists
        aicoder_dir = os.path.join(os.getcwd(), ".aicoder")
        os.makedirs(aicoder_dir, exist_ok=True)

        # Append to stats.log
        log_path = os.path.join(aicoder_dir, "stats.log")
        with open(log_path, "a") as f:
            f.write(log_line)

    # Register hook when assistant message is added (to estimate completion tokens)
    ctx.register_hook("after_assistant_message_added", _on_assistant_message)

    # Register hook to log after each AI response
    ctx.register_hook("after_ai_processing", _log_api_request)

    return {}
