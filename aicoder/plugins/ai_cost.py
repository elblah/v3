"""
AI Cost Plugin

Computes per-request cost live from the usage object using prices from env:

  PRICE_INPUT       $ per 1M non-cached input tokens  (required)
  PRICE_CACHE_READ  $ per 1M cache-read tokens        (optional, default 0)
  PRICE_CACHE_WRITE $ per 1M cache-creation tokens    (optional, default 0)
  PRICE_OUTPUT      $ per 1M output tokens            (required)
  PEAK_MULT         peak-hour price multiplier; feature on only when > 1.0
  PEAK_HOURS        UTC peak windows "01:00-04:00,06:00-10:00" (comma-separated,
                    wrap-around aware, e.g. "22:00-01:00")

Shows session cost in the context bar (dollars only, no cents). Inactive
unless PRICE_INPUT/PRICE_OUTPUT are set. Handles OpenAI-style and
Anthropic-style usage fields.

When PEAK_MULT > 1.0 and PEAK_HOURS has a valid window, the estimate is
multiplied by PEAK_MULT while the current UTC time is inside a peak window,
and the context bar shows a fire (🔥) right after the session cost.
Provider-reported costs are never multiplied.

Also complements stats_logger's JSONL entries via the on_stats_entry hook:
sets entry["cost_estimate"] (our env-var math) next to entry["cost"]
(provider-reported), so both stay in stats.log for deviation tracking.

Command:
  /ai-cost hint [S=2000] [K=20000] [G=4412] [P=0.05]
    Per-model compaction-point hint: toll-vs-rent balance from PRICE_*
    vars + live session measurement (growth G, drop rate P). S/K are
    quality dials (summary size, context kept), not derived by the math.

Token semantics (per provider):
- OpenAI:  prompt_tokens = TOTAL input; cached = prompt_tokens_details.cached_tokens;
           miss = prompt_tokens - cached (creation folded into miss price)
- Anthropic: input_tokens = miss only;
             cache_read_input_tokens; cache_creation_input_tokens
"""

import math
import os
from datetime import datetime, timezone

from aicoder.core.config import Config

_PRICES = None  # dict or None if plugin inactive
_PEAK = None    # dict(mult, windows) or None if peak feature off
_session_cost = 0.0     # per-request: reported cost wins, else estimate
_request_count = 0
_est_total = 0.0        # sum of env-var estimates (all requests)
_has_reported = False   # any provider-reported cost this session
_usage_history = []     # per-request (prompt_total, cache_read), capped


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


def _load_peak():
    """Load PEAK_MULT/PEAK_HOURS. Returns dict or None if feature off.

    Feature on only when PEAK_MULT > 1.0 AND at least one valid window.
    """
    try:
        mult = float(os.environ.get("PEAK_MULT", "") or 1.0)
    except (TypeError, ValueError):
        return None
    if mult <= 1.0:
        return None
    windows = _parse_windows(os.environ.get("PEAK_HOURS", ""))
    if not windows:
        return None
    return {"mult": mult, "windows": windows}


def _parse_windows(raw):
    """Parse '01:00-04:00,06:00-10:00' into (start, end) minute-of-day tuples.

    Wrap-around aware: '22:00-01:00' -> (1320, 60). Malformed tokens are
    skipped. End is exclusive.
    """
    windows = []
    for token in raw.split(","):
        token = token.strip()
        if "-" not in token:
            continue
        start_s, end_s = token.split("-", 1)
        start = _to_minutes(start_s.strip())
        end = _to_minutes(end_s.strip())
        if start is None or end is None or start == end:
            continue
        windows.append((start, end))
    return windows


def _to_minutes(hhmm):
    """'HH:MM' -> minutes since midnight, or None if malformed."""
    try:
        h, m = hhmm.split(":")
        h, m = int(h), int(m)
    except (TypeError, ValueError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def _minute_of_day(dt):
    """Minutes since midnight for a datetime (UTC in production, injectable in tests)."""
    return dt.hour * 60 + dt.minute


def _in_peak():
    """True if current UTC minute falls in any peak window."""
    if _PEAK is None:
        return False
    t = _minute_of_day(datetime.now(timezone.utc))
    for start, end in _PEAK["windows"]:
        if start <= end:
            if start <= t < end:
                return True
        elif t >= start or t < end:
            return True
    return False


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
    est = (miss * p["input"] + cache_read * p["cache_read"]
           + cache_write * p["cache_write"] + output * p["output"]) / 1_000_000
    if _PEAK is not None and _in_peak():
        est *= _PEAK["mult"]
    return est


def _extract_tokens(usage):
    """(prompt_total, cache_read) from a usage dict, or (None, None)."""
    if not isinstance(usage, dict):
        return None, None
    if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
        # Anthropic-style: input_tokens is miss only
        prompt = ((usage.get("input_tokens") or 0)
                  + (usage.get("cache_read_input_tokens") or 0)
                  + (usage.get("cache_creation_input_tokens") or 0))
        cache_read = usage.get("cache_read_input_tokens") or 0
    else:
        # OpenAI-style: prompt_tokens is total
        prompt = usage.get("prompt_tokens") or 0
        cache_read = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                      or usage.get("prompt_cache_hit_tokens") or 0)
    if not prompt:
        return None, None
    return prompt, cache_read


def _measured_growth(history):
    """Mean positive prompt growth per request; None without 3+ deltas."""
    deltas = [b[0] - a[0] for a, b in zip(history, history[1:]) if b[0] > a[0]]
    return sum(deltas) / len(deltas) if len(deltas) >= 3 else None


def _measured_drop_rate(history):
    """Fraction of eligible requests with cache_read ~0 (cache drop).

    First request excluded (legitimate full miss). Needs 5+ eligible.
    """
    eligible = [(pr, rd) for pr, rd in history[1:] if pr >= 2000]
    if len(eligible) < 5:
        return None
    drops = sum(1 for pr, rd in eligible if rd < pr * 0.1)
    return drops / len(eligible)


def _cmd_hint(args: str) -> None:
    """/ai-cost hint — per-model compaction point from prices + live session."""
    if _PRICES is None:
        print("[ai-cost] inactive: set PRICE_INPUT and PRICE_OUTPUT")
        return
    parts = (args or "").split()
    if not parts or parts[0] != "hint":
        print("usage: /ai-cost hint [S=2000] [K=20000] [G=4412] [P=0.05]")
        print("  S=summary tokens, K=context kept after compaction,")
        print("  G=growth tokens/request, P=drop probability (override measured)")
        return
    vals = {}
    for part in parts[1:]:
        if "=" not in part:
            print(f"[ai-cost] bad arg (want KEY=VALUE): {part}")
            return
        key, raw = part.split("=", 1)
        try:
            vals[key.strip().upper()] = float(raw)
        except ValueError:
            print(f"[ai-cost] bad number: {part}")
            return

    S = vals.get("S", 2000.0)
    K = vals.get("K", 20000.0)
    g = vals.get("G") or _measured_growth(_usage_history)
    p = vals.get("P")
    if p is None:
        p = _measured_drop_rate(_usage_history)
        drops_src = "measured" if p is not None else "assumed"
        p = 0.05 if p is None else p
    else:
        drops_src = "arg"
    p = min(max(p, 0.0), 1.0)

    m = _PRICES["input"]   # $/1M non-cached input (miss)
    x = _PRICES["output"]
    r_raw = os.environ.get("PRICE_CACHE_READ", "")
    r = None
    if r_raw.strip():
        try:
            r = float(r_raw)
        except ValueError:
            r = None

    print("--- /ai-cost hint ---")
    if g is None or g <= 0:
        print("need growth: 3+ requests this session, or pass G=tokens")
        return
    if r is None:
        r = m
        print(f"PRICE_CACHE_READ unset -> assuming NO cache discount (r={m:g})")
        print("set it (e.g. 0.015) for cached-price math")
    m_pt, r_pt, x_pt = m / 1e6, r / 1e6, x / 1e6
    print(f"prices $/1M: miss {m:g}  read {r:g}  out {x:g}")
    print(f"growth {g:,.0f} tok/req   drops {p * 100:.1f}% ({drops_src})")
    print(f"assumed: S={S:,.0f} summary  K={K:,.0f} kept after compaction")

    T = x_pt * S + m_pt * K  # one-time compaction toll, USD
    denom = g * (r_pt / 2 + p * (m_pt - r_pt) / 2)
    if denom <= 0:
        print("no rent (read>=miss, no drops): no optimum, compact freely")
        return
    k_star = math.sqrt(T / denom)
    c_star = K + k_star * g
    print(f"toll T = {x:g}*{S:,.0f} + {m:g}*{K:,.0f} = ${T:.4f} (once per cycle)")
    print(f"balance k* = {k_star:.1f} requests between compactions")
    if r >= m * 0.8:
        print("NO meaningful cache discount: rent is full price,")
        print("keep context SMALL and compact often.")
    print(f"COMPACT AT ~{c_star:,.0f} tokens")
    print(f"KEEP ~{K:,.0f} after compaction (summary + recent tail)")
    if c_star < 100000:
        extra = r_pt * (100000 - c_star)
        line = f"stretch to 100k costs +${extra:.4f}/req in reads"
        if r < m * 0.8:
            line += f"; a drop there costs {100000 / c_star:.1f}x one at C*"
        print(line)


def create_plugin(ctx):
    global _PRICES, _PEAK, _session_cost, _request_count, _est_total, _has_reported
    _PRICES = _load_prices()
    _PEAK = _load_peak()
    if _PRICES is None:
        return {}
    _session_cost = 0.0
    _request_count = 0
    _est_total = 0.0
    _has_reported = False
    _usage_history.clear()

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
        prompt, cache_read = _extract_tokens(usage)
        if prompt:
            _usage_history.append((prompt, cache_read))
            if len(_usage_history) > 200:
                del _usage_history[:len(_usage_history) - 200]

    def _on_session_change(*_args, **_kwargs):
        global _session_cost, _request_count, _est_total, _has_reported
        _session_cost = 0.0
        _request_count = 0
        _est_total = 0.0
        _has_reported = False
        _usage_history.clear()

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
        fire = ""
        if _PEAK is not None and _in_peak():
            fire = (f"{Config.colors['red']}{Config.colors['bold']}"
                    f"\U0001F525{Config.colors['reset']}")
        if _session_cost <= 0:
            return fire or None
        prefix = "\u2248" if not _has_reported else ""  # ~: estimate-only session
        dim, reset = Config.colors["dim"], Config.colors["reset"]
        return f"{dim}{prefix}${_session_cost:.4f}{reset}{fire}"

    ctx.register_hook("after_usage_data", _on_usage_data)
    ctx.register_hook("on_session_change", _on_session_change)
    ctx.register_hook("on_context_bar", _on_context_bar)
    ctx.register_hook("on_stats", _on_stats)
    ctx.register_hook("on_stats_entry", _on_stats_entry)
    ctx.register_command("ai-cost", _cmd_hint,
                         "Cost hint: per-model compaction point (/ai-cost hint)")

    return {}
