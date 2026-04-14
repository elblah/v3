"""
Filter plugin to remove <think>...</think> blocks from streamed AI responses<think>...</think> blocks from streamed AI responses.

Uses think_count for nesting, buffer-based tag matching, and flush on
stream end to never lose content.
"""

import sys
from aicoder.core.config import Config

OPEN_TAG = "<think>"
CLOSE_TAG = "</think>"
MAX_TAG_LEN = max(len(OPEN_TAG), len(CLOSE_TAG))


def create_plugin(ctx):
    """Plugin entry point"""

    state = {
        "think_count": 0,
        "buffer": "",
        "thinking_printed": False,
        "just_exited_think": False,
    }

    original_method = None

    def _is_partial_open_tag(s):
        """Check if s could be a partial match for OPEN_TAG."""
        return len(s) < len(OPEN_TAG) and OPEN_TAG.startswith(s)

    def _is_partial_close_tag(s):
        """Check if s could be a partial match for CLOSE_TAG."""
        return len(s) < len(CLOSE_TAG) and CLOSE_TAG.startswith(s)

    def _partial_tag_at_tail(text):
        """Return length of tail that could be a partial tag match."""
        max_check = min(MAX_TAG_LEN - 1, len(text))
        for length in range(max_check, 0, -1):
            tail = text[-length:]
            if _is_partial_open_tag(tail) or _is_partial_close_tag(tail):
                return length
        return 0

    def filter_content(content):
        """Filter content, removing think blocks."""
        if not content:
            return content

        # Strip leading whitespace from first chunk after exiting think block
        if state["just_exited_think"]:
            content = content.lstrip("\n\r\t ")
            state["just_exited_think"] = False
            if not content:
                return ""

        state["buffer"] += content
        buf = state["buffer"]
        result = []
        i = 0

        while i < len(buf):
            if state["think_count"] > 0:
                # Inside think block - look for close tag or nested open tag
                close_idx = buf.find(CLOSE_TAG, i)
                open_idx = buf.find(OPEN_TAG, i)

                next_close = close_idx if close_idx != -1 else len(buf)
                next_open = open_idx if open_idx != -1 else len(buf)

                if next_close == len(buf) and next_open == len(buf):
                    # No complete tag found - check partial at tail
                    partial = _partial_tag_at_tail(buf[i:])
                    if partial > 0:
                        # Keep potential partial match for next chunk
                        break
                    # No partial match possible, rest is just thinking content
                    i = len(buf)
                    break

                if next_close <= next_open:
                    # Found closing tag
                    i = close_idx + len(CLOSE_TAG)
                    state["think_count"] -= 1
                    if state["think_count"] == 0:
                        sys.stdout.write("\r\x1b[K")
                        sys.stdout.flush()
                        state["thinking_printed"] = False
                        state["just_exited_think"] = True
                        # Skip leading whitespace after think block
                        while i < len(buf) and buf[i] in "\n\r\t ":
                            i += 1
                else:
                    # Found nested opening tag
                    i = open_idx + len(OPEN_TAG)
                    state["think_count"] += 1
            else:
                # Outside think block - look for opening tag
                idx = buf.find(OPEN_TAG, i)
                if idx == -1:
                    # No tag found - output safe content, keep potential partial
                    partial = _partial_tag_at_tail(buf[i:])
                    safe_end = len(buf) - partial
                    if safe_end > i:
                        result.append(buf[i:safe_end])
                    i = safe_end
                    break

                # Output everything before the tag
                result.append(buf[i:idx])
                i = idx + len(OPEN_TAG)
                state["think_count"] = 1
                if not state["thinking_printed"]:
                    sys.stdout.write(
                        f"{Config.colors['dim']}thinking...{Config.colors['reset']}"
                    )
                    sys.stdout.flush()
                    state["thinking_printed"] = True

        state["buffer"] = buf[i:]
        return "".join(result)

    def flush_buffer(*args, **kwargs):
        """Flush any remaining buffer content (stream ended mid-think-block)."""
        if state["think_count"] > 0 and state["buffer"]:
            # Stream ended inside think block - output everything to not lose content
            sys.stdout.write("\r\x1b[K")
            sys.stdout.flush()
            sys.stdout.write(state["buffer"])
            sys.stdout.flush()
            state["buffer"] = ""
            state["think_count"] = 0
            state["thinking_printed"] = False

    def reset_state(*args, **kwargs):
        """Reset state for new turn."""
        state["think_count"] = 0
        state["buffer"] = ""
        state["thinking_printed"] = False
        state["just_exited_think"] = False

    def patched_method(self, content):
        """Patched version of print_with_colorization"""
        filtered = filter_content(content)
        return original_method(self, filtered)

    def apply_patch():
        nonlocal original_method
        from aicoder.core.markdown_colorizer import MarkdownColorizer
        original_method = MarkdownColorizer.print_with_colorization
        MarkdownColorizer.print_with_colorization = patched_method

    def remove_patch():
        nonlocal original_method
        if original_method:
            from aicoder.core.markdown_colorizer import MarkdownColorizer
            MarkdownColorizer.print_with_colorization = original_method

    apply_patch()

    ctx.register_hook("on_cleanup", remove_patch)
    ctx.register_hook("after_ai_processing", flush_buffer)
    ctx.register_hook("before_user_prompt", reset_state)

    return {
        "name": "filter_thinking",
        "description": "Removes think blocks from AI responses",
    }
