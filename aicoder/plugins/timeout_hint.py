"""
Timeout Hint Plugin - Nudge AI when streaming times out on large tool calls.

Listens to `on_stream_timeout` hook (raw SSE content string).
If the partial SSE contains a write_file/edit_file tool call, injects a
user message suggesting chunking.
"""

from aicoder.core.config import Config


_HINT = (
    "<system-reminder>\n"
    "SYSTEM: Your response timed out during streaming. "
    "You may be trying to do too much at once — "
    "large write/edit operations, or thinking through everything in one shot. "
    "Break the task into smaller, workable steps and complete them one at a time "
    "to stay within the response time limit.\n"
    "</system-reminder>"
)


def create_plugin(ctx):
    if not Config.streaming_enabled():
        return

    def _on_stream_timeout(raw_response: str):
        if '"write_file"' in raw_response or '"edit_file"' in raw_response:
            ctx.app.message_history.add_user_message(_HINT)

    ctx.register_hook("on_stream_timeout", _on_stream_timeout)
