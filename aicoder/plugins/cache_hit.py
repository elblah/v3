"""
Cache Hit Plugin

Tracks cache hit percentage from usage objects across three views:

- Session:          rolling token-weighted hit rate since /new or /load
- Last req:         hit rate of the most recent request
- Since compaction: rolling rate reset on after_compaction — shows provider
                    cache health on the current conversation

Shows these in /stats output (on_stats hook), active by default. Context
bar display is opt-in: CACHE_HIT_BAR=1.

Token semantics (per provider, mirrors ai_cost.py):
- OpenAI:  prompt_tokens = TOTAL input; cached = prompt_tokens_details.cached_tokens
- Anthropic: input_tokens = miss only; cache_read_input_tokens; cache_creation_input_tokens

Env:
    CACHE_HIT_BAR=1  (show "hit NN%" in context bar, default: off)
"""

from aicoder.core.config import Config
from aicoder.utils.bool_utils import env_bool

_session_hit = 0
_session_total = 0
_session_reqs = 0
_last_hit = 0
_last_total = 0
_compact_hit = 0
_compact_total = 0


def _extract_cache_totals(usage):
    """Return (hit_tokens, total_input_tokens) for one usage dict.

    Returns (None, 0) if cache data is missing or unusable — i.e. provider
    never reported cache fields, or total is 0. A request that reports
    cache fields with 0 cached tokens is a real full-miss and counts as
    (0, total) — skipping it would inflate the rate.
    Total counts only input tokens; hit rate = hit / total.
    """
    if not isinstance(usage, dict):
        return None, 0

    if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
        # Anthropic-style: input_tokens = miss only
        hit = usage.get("cache_read_input_tokens") or 0
        miss = usage.get("input_tokens") or 0
        creation = usage.get("cache_creation_input_tokens") or 0
        total = miss + hit + creation
    else:
        # OpenAI-style: prompt_tokens includes cached
        if ("prompt_tokens_details" not in usage
                and "prompt_cache_hit_tokens" not in usage):
            return None, 0
        ptd = usage.get("prompt_tokens_details") or {}
        hit = ptd.get("cached_tokens") or usage.get("prompt_cache_hit_tokens") or 0
        total = usage.get("prompt_tokens") or 0

    if total <= 0:
        return None, 0
    return int(hit), int(total)


def _on_usage_data(usage) -> None:
    global _session_hit, _session_total, _session_reqs, _last_hit, _last_total
    global _compact_hit, _compact_total
    hit, total = _extract_cache_totals(usage)
    if hit is None:
        return
    _session_hit += hit
    _session_total += total
    _session_reqs += 1
    _last_hit, _last_total = hit, total
    _compact_hit += hit
    _compact_total += total


def _on_session_change(*_args, **_kwargs) -> None:
    global _session_hit, _session_total, _session_reqs, _last_hit, _last_total
    global _compact_hit, _compact_total
    _session_hit = _session_total = _session_reqs = 0
    _last_hit = _last_total = 0
    _compact_hit = _compact_total = 0


def _on_after_compaction(*_args, **_kwargs) -> None:
    global _compact_hit, _compact_total
    _compact_hit = 0
    _compact_total = 0


def _on_stats(stats):
    """Contribute lines to /stats output."""
    if _session_total <= 0:
        return None
    lines = [
        "--- Cache Hit ---",
        f"  {'Session:':<17}{_session_hit / _session_total * 100:.1f}%"
        f" ({_session_hit:,} / {_session_total:,} tok, {_session_reqs} reqs)",
    ]
    if _last_total > 0:
        lines.append(
            f"  {'Last req:':<17}{_last_hit / _last_total * 100:.1f}%"
            f" ({_last_hit:,} / {_last_total:,} tok)"
        )
    if _compact_total > 0:
        lines.append(
            f"  {'Since compaction:':<17}{_compact_hit / _compact_total * 100:.1f}%"
            f" ({_compact_hit:,} / {_compact_total:,} tok)"
        )
    return lines


def _on_context_bar():
    """Context bar line — only when CACHE_HIT_BAR=1."""
    if not env_bool("CACHE_HIT_BAR") or _session_total <= 0:
        return None
    pct = _session_hit / _session_total * 100
    return f"{Config.colors['dim']}hit {pct:.0f}%{Config.colors['reset']}"


def create_plugin(ctx):
    def _reset(*_args, **_kwargs):
        _on_session_change()

    ctx.register_hook("after_usage_data", _on_usage_data)
    ctx.register_hook("on_session_change", _reset)
    ctx.register_hook("after_compaction", _on_after_compaction)
    ctx.register_hook("on_stats", _on_stats)
    ctx.register_hook("on_context_bar", _on_context_bar)
    return {}
