"""
Multi-Key Rotation Plugin - Split API keys by ___ and rotate on 429.

OPENAI_API_KEY="sk-proj-abc123___sk-proj-def456___sk-proj-ghi789..."

On 429: rotate to next key immediately (circular, wraps to first key).
On success: stay on current key.

Env:
  KEY_ROTATE_SEPARATOR - separator char (default: ___)
  KEY_ROTATE_DEBUG     - set to 1/true for debug logging
"""

import os
import sys
from typing import Optional

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


_SEPARATOR = os.environ.get("KEY_ROTATE_SEPARATOR", "___")
_DEBUG = os.environ.get("KEY_ROTATE_DEBUG", "").lower() in ("1", "true", "yes")

_keys: list[str] = []
_key_index: int = 0


def _log(msg: str):
    if _DEBUG and sys.stdout.isatty():
        LogUtils.warn(f"\n[key-rotate] {msg}")


def create_plugin(ctx):
    raw = Config.api_key()
    if not raw:
        return

    parts = [k.strip() for k in raw.split(_SEPARATOR) if k.strip()]
    if len(parts) <= 1:
        return  # single key, nothing to rotate

    global _keys
    _keys = parts
    os.environ["OPENAI_API_KEY"] = _keys[0]
    _log(f"loaded {len(_keys)} keys, active: #1")

    ctx.register_hook("on_api_error", _on_error)
    ctx.register_hook("on_context_bar", _on_context_bar)


def _rotate() -> bool:
    """Rotate to next key (wraps around)."""
    global _key_index
    _key_index = (_key_index + 1) % len(_keys)
    new_key = _keys[_key_index]
    os.environ["OPENAI_API_KEY"] = new_key
    mask = new_key[:8] + "..." if len(new_key) > 8 else new_key
    _log(f"rotated to #{_key_index + 1}/{len(_keys)} ({mask})")
    return True


def _on_error(msg: str, status: int):
    if status != 429 or not _keys:
        return
    _rotate()


def _on_context_bar() -> Optional[str]:
    """Hook: show active key position in context bar."""
    if not _keys:
        return None
    d = Config.colors["dim"]
    r = Config.colors["reset"]
    return f"{d}k={_key_index+1}/{len(_keys)}{r}"
