"""
AI Cost Plugin

Computes per-request cost live from the usage object using prices from env:

  PRICE_INPUT       $ per 1M non-cached input tokens  (required)
  PRICE_CACHE_READ  $ per 1M cache-read tokens        (optional, default 0)
  PRICE_CACHE_WRITE $ per 1M cache-creation tokens    (optional, default 0)
  PRICE_OUTPUT      $ per 1M output tokens            (required)

Shows session cost in the context bar. Inactive unless PRICE_INPUT/PRICE_OUTPUT
are set. Handles OpenAI-style and Anthropic-style usage fields.

Token semantics (per provider):
- OpenAI:  prompt_tokens = TOTAL input; cached = prompt_tokens_details.cached_tokens;
           miss = prompt_tokens - cached (creation folded into miss price)
- Anthropic: input_tokens = miss only; cache_read_input_tokens; cache_creation_input_tokens
"""

import os
from aicoder.core.config import Config

_PRICES = None  # dict or None if plugin inactive
_session_cost = 0.0
_request_count = 0


def _load_prices():
    """Load PRICE_* env vars. Returns dict or None if input/output prices missing."""
    def _get(name):
        raw = os.environ.get(name, "")
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    p_in = _get("PRICE_INPUT")
    p_out = _get("PRICE_OUTPUT")
    if p_in is None or p_out is None:
        return None
    return {
        "input": p_in,
        "cache_read": _get("PRICE_CACHE_READ") or 0.0,
        "cache_write": _get("PRICE_CACHE_WRITE") or 0.0,
        "output": p_out,
    }


def _reported_cost(usage):
    """Provider-reported USD cost if present, else None (mirrors stats_logger._extract_cost)."""
    cost_details = usage.get("cost_details") or {}
    for key in ("upstream_inference_cost", "upstream_inference_prompt_cost"):
        val = cost_details.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    cost_obj = usage.get("cost")
    if isinstance(cost_obj, dict):
        val = cost_obj.get("usd")
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    if isinstance(cost_obj, (int, float)) and cost_obj > 0:
        return float(cost_obj)
    return None


def _request_cost(usage):
    """Cost (USD) of one usage dict. Prefers provider-reported cost, else estimates
    from tokens x PRICE_* env vars. Returns 0 if neither possible."""
    if not isinstance(usage, dict) or _PRICES is None:
        return 0.0

    reported = _reported_cost(usage)
    if reported is not None:
        return reported

    output = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    prompt_details = usage.get("prompt_tokens_details") or {}

    if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
        # Anthropic-style: input_tokens is miss only
        miss = usage.get("input_tokens") or 0
        cache_read = usage.get("cache_read_input_tokens") or 0
        cache_write = usage.get("cache_creation_input_tokens") or 0
    else:
        # OpenAI-style: prompt_tokens includes cached; creation folded into miss
        prompt = usage.get("prompt_tokens") or 0
        cache_read = (prompt_details.get("cached_tokens")
                      or usage.get("prompt_cache_hit_tokens") or 0)
        miss = max(0, prompt - cache_read)
        cache_write = 0

    p = _PRICES
    return (miss * p["input"] + cache_read * p["cache_read"]
            + cache_write * p["cache_write"] + output * p["output"]) / 1_000_000


def create_plugin(ctx):
    global _PRICES
    _PRICES = _load_prices()
    if _PRICES is None:
        return {}

    def _on_usage_data(usage):
        global _session_cost, _request_count
        cost = _request_cost(usage)
        if cost > 0:
            _session_cost += cost
            _request_count += 1

    def _on_session_change(*_args, **_kwargs):
        global _session_cost, _request_count
        _session_cost = 0.0
        _request_count = 0

    def _on_stats(stats):
        """Contribute lines to /stats output."""
        if _session_cost <= 0:
            return None
        avg = _session_cost / _request_count if _request_count else 0.0
        return [
            "--- AI Cost ---",
            f"  Session Cost: ${_session_cost:.4f}",
            f"  Requests: {_request_count} (avg ${avg:.4f}/req)",
        ]

    def _on_context_bar():
        if _session_cost <= 0:
            return None
        # Show in cents if < $1, dollars if >= $1
        if _session_cost < 1.0:
            cost_str = f"c{_session_cost * 100:.1f}¢"
        else:
            cost_str = f"c${_session_cost:.4f}"
        return f"{Config.colors['dim']}{cost_str}{Config.colors['reset']}"

    ctx.register_hook("after_usage_data", _on_usage_data)
    ctx.register_hook("on_session_change", _on_session_change)
    ctx.register_hook("on_context_bar", _on_context_bar)
    ctx.register_hook("on_stats", _on_stats)

    return {}
