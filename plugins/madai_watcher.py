"""
madai_watcher.py - Context size monitoring with save_progress reminders

Monitors conversation context size and injects user messages with reminders
to save_progress before auto-compaction happens.

Install this plugin alongside madai.py if you want context warnings.

Thresholds:
- 25%: Gentle suggestion
- 50%: Stronger reminder
- 70%: Urgent warning (last chance before compaction)

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
    _counter = 0  # How many messages ago we last warned
    _last_range = -1  # Track previous range level to detect changes

    def _reset_all():
        """Reset counter - called by madai after save_progress"""
        nonlocal _counter
        _counter = 0
        # Keep _last_range - if range is same, counter continues

    def _get_range_level(current_size, max_size):
        """Return range level: -1=below 25%, 0=gentle, 1=strong, 2=urgent"""
        percentage = (current_size / max_size) * 100

        if percentage >= 70:
            return 2  # urgent
        if percentage >= 50:
            return 1  # strong
        if percentage >= 25:
            return 0  # gentle
        return -1  # below threshold

    def _get_warning_message(level):
        """Build warning message based on level"""
        if level == 2:  # urgent
            return "Save progress NOW! Compaction will happen soon. Call save_progress NOW!"
        if level == 1:  # strong
            return "Save progress NOW! Call save_progress tool."
        return "please save_progress when you have a moment to organize your thoughts"  # gentle

    def _check_context(has_tool_calls=None):
        """Check context size and inject warning if needed"""
        nonlocal _counter, _last_range

        stats = app.stats
        current_size = stats.current_prompt_size or 0
        max_size = Config.context_size()

        debug = Config.debug()
        if debug:
            print(f"[madai_watch] Hook called - context: {current_size}/{max_size} ({100*current_size/max_size:.0f}%)")

        current_range = _get_range_level(current_size, max_size)

        # Below threshold, no warning needed
        if current_range < 0:
            if debug:
                print(f"[madai_watch] Below threshold (25%), no warning")
            return

        # Range changed? Warn immediately and reset
        if current_range > _last_range:
            _counter = 0
            _last_range = current_range
            level_name = ["gentle", "strong", "urgent"][current_range]
            if debug:
                print(f"[madai_watch] WARNING! Range changed to {level_name}")
            warning = _get_warning_message(current_range)
            if debug:
                print(f"[madai_watch] Injecting warning: '{warning}'")
            app.message_history.add_user_message(warning)
            return

        # Same range, use counter
        if _counter < _warn_interval:
            _counter += 1
            if debug:
                print(f"[madai_watch] Counter: {_counter}/{_warn_interval}, not warning")
            return

        # Counter reached, warn
        _counter = 0
        _last_range = current_range
        level_name = ["gentle", "strong", "urgent"][current_range]
        if debug:
            print(f"[madai_watch] WARNING! Level: {level_name}")
        warning = _get_warning_message(current_range)
        if debug:
            print(f"[madai_watch] Injecting warning: '{warning}'")
        app.message_history.add_user_message(warning)

    # Register hooks
    ctx.register_hook("after_ai_processing", _check_context)
    ctx.register_hook("madai_progress_saved", _reset_all)
    ctx.register_hook("on_session_change", _reset_all)

    if Config.debug():
        print("[+] madai_watcher plugin loaded")
        print(f"  - Warning interval: every {_warn_interval} turns")
        print("  - Thresholds: 25% (gentle), 50% (strong), 70% (urgent)")
