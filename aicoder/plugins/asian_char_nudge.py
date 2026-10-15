"""
asian_char_nudge.py - Auto re-ask when the AI outputs non-Latin characters

Detects CJK, Arabic, Devanagari, Thai, and other non-Latin scripts in AI
responses. When found, triggers an immediate new AI turn (set_next_prompt)
asking it to make itself comprehensible in the user's language — the user
does not have to type anything. Prints a yellow status line so the user can
see the nudge happened.

Once the retry limit is hit for consecutive offending replies, it stops
auto-asking and falls back to a silent reminder message.

Env:
    ASIAN_NUDGE=1       enable at startup (default: disabled)
    ASIAN_NUDGE_DEBUG=1 verbose logging

Commands:
    /asian-nudge        show status
    /asian-nudge on|off session toggle (env var is the persistent setting)
"""

import re
import time

from aicoder.core.config import Config
from aicoder.utils.bool_utils import TRUTHY, FALSY, env_bool
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

# Consecutive offending replies we auto-re-ask before giving up and just
# leaving a reminder. Prevents an endless auto-retry loop (and its cost).
_MAX_AUTO_RETRIES = 2

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

    debug = env_bool("ASIAN_NUDGE_DEBUG")

    state = {
        "enabled": env_bool("ASIAN_NUDGE"),
        "count": 0,
        "streak": 0,
        "last_reminder": 0.0,
    }
    cooldown = 30  # seconds between reminder-only fallbacks

    def _status(msg):
        c = Config.colors
        tag = f"{c['bold']}{c['yellow']}[asian_char_nudge]{c['reset']}"
        LogUtils.print(f"\n\n{tag} {msg}")

    def _on_assistant_message_added(message: dict) -> None:
        if not state["enabled"]:
            return

        text = _extract_text(message)
        if not text:
            return

        if not _NON_LATIN_RE.search(text):
            state["streak"] = 0  # clean reply ends the retry streak
            return

        state["count"] += 1

        if debug:
            c = Config.colors
            matches = _NON_LATIN_RE.findall(text)
            sample = "".join(matches[:20])
            LogUtils.print(
                f"{c['yellow']}[asian-nudge] #{state['count']} "
                f"non-Latin chars detected ({len(matches)} total, "
                f"sample: {sample}){c['reset']}"
            )

        if state["streak"] < _MAX_AUTO_RETRIES:
            state["streak"] += 1
            app.set_next_prompt(NUDGE_MESSAGE)
            _status(
                f"non-Latin chars in reply — auto re-asking in your language "
                f"({state['streak']}/{_MAX_AUTO_RETRIES})"
            )
            return

        # Retry limit hit — leave a silent reminder instead of another turn
        now = time.time()
        if now - state["last_reminder"] < cooldown:
            return
        state["last_reminder"] = now
        state["streak"] = 0
        app.message_history.add_user_message(NUDGE_MESSAGE)
        _status("non-Latin chars in reply — retry limit hit, reminder only")

    def _handle_command(args_str: str) -> str:
        parts = args_str.strip().split() if args_str else []

        if not parts:
            on_off = "enabled" if state["enabled"] else "disabled"
            return (
                f"Asian char nudge: {on_off}\n"
                f"\n"
                f"- non-Latin chars seen this session: {state['count']}\n"
                f"- auto re-asks before falling back to a reminder: {_MAX_AUTO_RETRIES}\n"
                f"\n"
                f"Commands:\n"
                f"- /asian-nudge on|off - toggle for this session\n"
                f"- ASIAN_NUDGE=1 in the environment - persistent setting\n"
            )

        if parts[0] in TRUTHY:
            state["enabled"] = True
            return "Asian char nudge enabled (this session)"
        if parts[0] in FALSY:
            state["enabled"] = False
            state["streak"] = 0
            return "Asian char nudge disabled (this session)"

        return "Usage: /asian-nudge [on|off]"

    ctx.register_hook("after_assistant_message_added", _on_assistant_message_added)
    ctx.register_command(
        "/asian-nudge", _handle_command, description="Re-ask when replies contain non-Latin characters"
    )

    if debug:
        LogUtils.print(f"[asian-nudge] loaded (enabled={state['enabled']})")
