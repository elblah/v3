"""
asian_char_nudge.py - Nudge AI when it outputs non-Latin characters

Detects CJK, Arabic, Devanagari, Thai, and other non-Latin scripts in AI
responses. When found, silently injects a <system-reminder> into history
telling the AI the user can't read those characters.

Env:
    ASIAN_NUDGE=0       disable (default: enabled)
    ASIAN_NUDGE_DEBUG=1 verbose logging
"""

import os
import re
import time

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Unicode ranges covering CJK, Arabic, Indic, Thai, etc.
# Excludes common symbols, math, emoji, punctuation blocks.
_NON_LATIN_RE = re.compile(
    '['
    '\u4e00-\u9fff'   # CJK Unified Ideographs
    '\u3400-\u4dbf'   # CJK Extension A
    '\uf900-\ufaff'   # CJK Compatibility Ideographs
    '\u3040-\u309f'   # Hiragana
    '\u30a0-\u30ff'   # Katakana
    '\uac00-\ud7af'   # Hangul Syllables
    '\u1100-\u11ff'   # Hangul Jamo
    '\ua960-\ua97f'   # Hangul Jamo Extended-A
    '\ud7b0-\ud7ff'   # Hangul Jamo Extended-B
    '\u0600-\u06ff'   # Arabic
    '\u0750-\u077f'   # Arabic Supplement
    '\u08a0-\u08ff'   # Arabic Extended-A
    '\u0900-\u097f'   # Devanagari
    '\u0980-\u09ff'   # Bengali
    '\u0a00-\u0a7f'   # Gurmukhi
    '\u0a80-\u0aff'   # Gujarati
    '\u0b00-\u0b7f'   # Oriya
    '\u0b80-\u0bff'   # Tamil
    '\u0c00-\u0c7f'   # Telugu
    '\u0c80-\u0cff'   # Kannada
    '\u0d00-\u0d7f'   # Malayalam
    '\u0e00-\u0e7f'   # Thai
    '\u0e80-\u0eff'   # Lao
    '\u1000-\u109f'   # Myanmar
    '\u1780-\u17ff'   # Khmer
    '\u1800-\u18af'   # Mongolian
    '\u0d80-\u0dff'   # Sinhala
    '\u0f00-\u0fff'   # Tibetan
    '\u1200-\u137f'   # Ethiopic
    '\u2e80-\u2eff'   # CJK Radicals Supplement
    '\u2f00-\u2fdf'   # Kangxi Radicals
    '\u3000-\u303f'   # CJK Symbols and Punctuation
    '\u31c0-\u31ef'   # CJK Strokes
    '\u3200-\u32ff'   # Enclosed CJK Letters and Months
    '\u3300-\u33ff'   # CJK Compatibility
    '\ufe30-\ufe4f'   # CJK Compatibility Forms
    '\uff00-\uffef'   # Halfwidth and Fullwidth Forms
    ']'
)

NUDGE_MESSAGE = (
    "<system-reminder>\n"
    "Your previous response contained characters from a language the user "
    "doesn't speak (Chinese, Japanese, Korean, Arabic, etc). If the meaning "
    "of those characters matters for communication, make sure the message is "
    "comprehensible without depending on them — translate or explain in the "
    "user's language (infer it from context). If the characters were just "
    "decorative or incidental, simply avoid them going forward.\n"
    "</system-reminder>"
)


def _extract_text(msg: dict) -> str:
    """Extract text content from a message dict."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)
    return ""


def create_plugin(ctx):
    app = ctx.app

    enabled = os.environ.get("ASIAN_NUDGE", "").lower()
    enabled = enabled in ("1", "true", "yes", "on")
    debug = os.environ.get("ASIAN_NUDGE_DEBUG", "").lower() in ("1", "true", "yes")

    if not enabled:
        return

    state = {"count": 0, "last_nudge": 0.0}
    cooldown = 30  # seconds between nudges

    def _on_assistant_message_added(message: dict) -> None:
        text = _extract_text(message)
        if not text:
            return

        if not _NON_LATIN_RE.search(text):
            return

        now = time.time()
        if now - state["last_nudge"] < cooldown:
            return

        state["count"] += 1
        state["last_nudge"] = now

        app.message_history.add_user_message(NUDGE_MESSAGE)

        if debug:
            c = Config.colors
            matches = _NON_LATIN_RE.findall(text)
            sample = "".join(matches[:20])
            LogUtils.print(
                f"{c['yellow']}[asian-nudge] #{state['count']} "
                f"non-Latin chars detected ({len(matches)} total, "
                f"sample: {sample}){c['reset']}"
            )

    ctx.register_hook("after_assistant_message_added", _on_assistant_message_added)

    if debug:
        LogUtils.print(f"[asian-nudge] loaded (enabled={enabled})")
