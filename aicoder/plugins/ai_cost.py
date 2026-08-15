"""
AI Cost Plugin

Computes per-request cost live from the usage object using prices from env:

  PRICE_INPUT       $ per 1M non-cached input tokens  (required)
  PRICE_CACHE_READ  $ per 1M cache-read tokens        (optional, default 0)
  PRICE_CACHE_WRITE $ per 1M cache-creation tokens    (optional, default 0)
  PRICE_OUTPUT      $ per 1M output tokens            (required)

Shows session cost in the context bar (dollars only, no cents). Inactive
unless PRICE_INPUT/PRICE_OUTPUT are set. Handles OpenAI-style and
Anthropic-style usage fields.

Also complements stats_logger's JSONL entries via the on_stats_entry hook:
sets entry["cost_estimate"] (our env-var math) next to entry["cost"]
(provider-reported), so both stay in stats.log for deviation tracking.

Token semantics (per provider):
- OpenAI:  prompt_tokens = TOTAL input; cached = prompt_tokens_details.cached_tokens;
           miss = prompt_tokens - cached (creation folded into miss price)
- Anthropic: input_tokens = miss only;
             cache_read_input_tokens; cache_creation_input_tokens
"""

import os
from aicoder.core.config import Config

_PRICES = None  # dict or None if plugin inactive
_session_cost = 0.0     # per-request: reported cost wins, else estimate
_request_count = 0
_est_total = 0.0        # sum of env-var estimates (all requests)
_has_reported = False   # any provider-reported cost this session


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
    """Provider-reported USD cost if present, else None (mirrors stats_logger)."""
    if not isinstance(usage, dict):
        return None
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


def _estimate_cost(usage):
    """Estimated USD cost from tokens x PRICE_* env vars. 0.0 if no tokens."""
    if not isinstance(usage, dict) or _PRICES is None:
        return 0.0

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
    global _PRICES, _session_cost, _request_count, _est_total, _has_reported
    _PRICES = _load_prices()
    if _PRICES is None:
        return {}
    _session_cost = 0.0
    _request_count = 0
    _est_total = 0.0
    _has_reported = False

    def _on_usage_data(usage):
        global _session_cost, _request_count, _est_total, _has_reported
        reported = _reported_cost(usage)
        est = _estimate_cost(usage)
        cost = reported if reported is not None else est
        if cost > 0:
            _session_cost += cost
            _request_count += 1
            _est_total += est
            if reported is not None:
                _has_reported = True

    def _on_session_change(*_args, **_kwargs):
        global _session_cost, _request_count, _est_total, _has_reported
        _session_cost = 0.0
        _request_count = 0
        _est_total = 0.0
        _has_reported = False

    def _on_stats_entry(entry):
        """Complement stats_logger JSONL entry with our env-var estimate."""
        if isinstance(entry, dict):
            entry["cost_estimate"] = _estimate_cost(entry.get("usage") or {})

    def _on_stats(stats):
        """Contribute lines to /stats output.

        "Session Cost" is printed only when the provider reported a cost
        (bar shows `≈$X` in the other case). With no reported cost the
        session value is purely an estimate, so only "Estimated:" shows —
        "Session Cost" always means provider-reported.
        """
        if _session_cost <= 0:
            return None
        avg = _session_cost / _request_count if _request_count else 0.0
        lines = ["--- AI Cost ---"]
        if _has_reported:
            lines.append(f"  Session Cost: ${_session_cost:.4f}")
            if _est_total > 0:
                lines.append(f"  Estimated:    ${_est_total:.4f}")
        else:
            lines.append(f"  Estimated:    ${_est_total:.4f}")
        lines.append(f"  Requests: {_request_count} (avg ${avg:.4f}/req)")
        return lines

    def _on_context_bar():
        if _session_cost <= 0:
            return None
        prefix = "\u2248" if not _has_reported else ""  # ~: estimate-only session
        dim, reset = Config.colors["dim"], Config.colors["reset"]
        return f"{dim}{prefix}${_session_cost:.4f}{reset}"

    ctx.register_hook("after_usage_data", _on_usage_data)
    ctx.register_hook("on_session_change", _on_session_change)
    ctx.register_hook("on_context_bar", _on_context_bar)
    ctx.register_hook("on_stats", _on_stats)
    ctx.register_hook("on_stats_entry", _on_stats_entry)

    return {}
