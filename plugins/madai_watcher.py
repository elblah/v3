"""
madai_watcher.py - Context size monitoring with save_progress reminders

Monitors conversation context size and injects user messages with reminders
to save_progress before auto-compaction happens.

Install this plugin alongside madai.py if you want context warnings.

Thresholds:
- 25%: Gentle suggestion
- 50%: Stronger reminder
- 70%: Urgent warning
- Compaction threshold: Compaction imminent

Config:
- CONTEXT_WARN_INTERVAL=10 (warn every N turns, default 10)
"""

import os
from aicoder.core.config import Config


def create_plugin(ctx):
    """Create madai watcher plugin"""
    app = ctx.app

    # Configurable warning interval
    _warn_interval = int(os.environ.get("CONTEXT_WARN_INTERVAL", "10"))
    _turn_counter = 0

    def _get_warn_interval():
        return _warn_interval

    def _reset_counter():
        nonlocal _turn_counter
        _turn_counter = 0

    def _check_context_and_warn(has_tool_calls=None):
        """Check context size and inject warning if needed"""
        nonlocal _turn_counter

        stats = app.stats
        current_size = stats.current_prompt_size or 0
        max_size = Config.context_size()
        compact_threshold = Config.auto_compact_threshold()

        if compact_threshold <= 0:
            return  # Auto-compaction disabled

        percentage = (current_size / max_size) * 100

        # Determine warning level
        if current_size >= compact_threshold:
            # Urgent - compaction imminent
            level = "urgent"
        elif percentage >= 70:
            level = "urgent"
        elif percentage >= 50:
            level = "strong"
        elif percentage >= 25:
            level = "gentle"
        else:
            return  # No warning needed

        # Check if we should warn this turn
        should_warn = _turn_counter >= _get_warn_interval()

        # Also warn if level increased (e.g., gentle -> strong)
        # This is tracked by checking if higher level warnings exist
        messages = app.message_history.get_messages()
        has_urgent = any("[CONTEXT WARNING] Compaction imminent" in msg.get("content", "") for msg in messages)
        has_strong = any("[CONTEXT WARNING] Context at" in msg.get("content", "") and percentage >= 50 for msg in messages)
        has_gentle = any("[CONTEXT INFO] Context at" in msg.get("content", "") for msg in messages)

        level_increased = (
            (level == "urgent" and not has_urgent) or
            (level == "strong" and not has_strong and not has_urgent) or
            (level == "gentle" and not has_gentle and not has_strong and not has_urgent)
        )

        if not should_warn and not level_increased:
            _turn_counter += 1
            return

        # Reset counter after warning
        _turn_counter = 0

        # Build warning message
        if level == "urgent":
            warning = (
                f"[CONTEXT WARNING] Context at {current_size:,} tokens ({percentage:.0f}% full). "
                f"Compaction threshold: {compact_threshold:,} tokens. "
                f"Call save_progress NOW to preserve context before compaction!"
            )
        elif level == "strong":
            warning = (
                f"[CONTEXT WARNING] Context at {current_size:,} tokens ({percentage:.0f}% full). "
                f"Approaching compaction threshold. Consider save_progress soon."
            )
        else:  # gentle
            warning = (
                f"[CONTEXT INFO] Context at {current_size:,} tokens ({percentage:.0f}% full). "
                f"Consider save_progress when you've made significant progress."
            )

        # Inject warning as user message
        app.message_history.add_user_message(warning)

    def _on_session_change():
        """Reset counter on session change"""
        _reset_counter()

    # Register hooks
    ctx.register_hook("before_user_prompt", _check_context_and_warn)
    ctx.register_hook("after_ai_processing", _check_context_and_warn)
    ctx.register_hook("on_session_change", _on_session_change)

    if Config.debug():
        print("[+] madai_watcher plugin loaded")
        print(f"  - Warning interval: every {_warn_interval} turns")
        print("  - Thresholds: 25% (gentle), 50% (strong), 70% (urgent)")
