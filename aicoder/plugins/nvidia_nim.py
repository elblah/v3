"""
NVIDIA NIM Plugin - Smart model rotation for NVIDIA's free API.

Auto-activates when OPENAI_BASE_URL == https://integrate.api.nvidia.com/v1.

Two modes:
  - API_MODEL=auto            → plugin picks best model, auto-rotates on 429/slow
  - API_MODEL=<concrete ID>   → plugin provides /nvidia commands only, no rotation

Features:
  - Maintains ordered preference list of tool_call+reasoning models
  - Detects 429 rate limits and rotates to next available model
  - Configurable cooldown per model (env var NVIDIA_NIM_COOLDOWN)
  - Caches filtered NVIDIA model data from models.dev in .aicoder/models.json
  - Stale cache preserved if refresh fails — never lose last good data

Env vars:
  NVIDIA_NIM_ORDER     - comma-separated model ID preference list
  NVIDIA_NIM_COOLDOWN  - comma-separated model:seconds (e.g., glm:1800,kimi:1200)

Commands:
  /nvidia status   - current model, cooldowns, preference
  /nvidia list     - available models with tool_call+reasoning
  /nvidia set ID   - force a specific model
  /nvidia refresh  - refresh model cache from models.dev
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# ── Constants ──────────────────────────────────────────────────────
_RECOVERY_RATE = 5.0   # rep points recovered per minute toward base
_SLOW_PENALTY = 10.0   # rep penalty for <3 tok/s
_429_PENALTY = 10.0    # rep penalty for 429
_404_PENALTY = 20.0    # rep penalty for 404 (model unavailable/deprecated)
_FAST_BONUS = 1.0      # rep bonus for fast responses

# ── Runtime state ───────────────────────────────────────────────────
NIM_URL = "https://integrate.api.nvidia.com/v1"

_models: List[Dict] = []
_preference: List[str] = []
_reputation: Dict[str, float] = {}  # model_id → score (100=none, lower=sinned)
_current_model: str = ""
_req_start: float = 0.0
_req_model: str = ""
_lock = threading.Lock()

# Reasoning format for NVIDIA — always "openai" (OpenAI-compatible API).
# NVIDIA doesn't support the `thinking` extra_body that "deepseek"/"glm"
# formats send. Only top-level `reasoning_effort` works.
_MODEL_FMT: dict = {}

# Default preference order — by coding score (benchmark), user overrides applied:
#   DeepSeek V4 Flash preferred over MiniMax-M3
#   DeepSeek V4 Pro demoted (very slow on NIM despite high coding)
# Models not in list appended at end sorted by context.
_DEFAULT_ORDER = [
    "z-ai/glm-5.2",                                 # coding 68.8
    "deepseek-ai/deepseek-v4-flash",                 # coding 56.2 — user prefers over M3
    "minimaxai/minimax-m3",                          # coding 58.6
    "moonshotai/kimi-k2.6",                          # coding 56.0
    "minimaxai/minimax-m2.7",                        # coding 52.6
    "deepseek-ai/deepseek-v4-pro",                   # coding 59.4 — demoted (slow on NIM)
    "nvidia/nemotron-3-ultra-550b-a55b",             # coding 49.3
    "qwen/qwen3.5-397b-a17b",                        # coding 48.2
    "google/gemma-4-31b-it",                         # coding 43.4
    "nvidia/nemotron-3-super-120b-a12b",             # coding 37.7
    "stepfun-ai/step-3.7-flash",                     # coding 37.3
    "openai/gpt-oss-120b",                           # coding 30.4
    "mistralai/mistral-small-4-119b-2603",           # coding 26.6
    "openai/gpt-oss-20b",                            # coding 20.7
]


# ── Plugin entry ─────────────────────────────────────────────────────
def create_plugin(ctx):
    base = Config.base_url().rstrip("/")
    if base != NIM_URL:
        return

    _load_cache()
    _load_rep()
    _load_preference()

    model = Config.model()
    if model != "auto":
        # Manual mode — user chose a specific model, plugin only provides commands
        ctx.register_command("nvidia", _cmd, "NVIDIA NIM model management")
        if Config.debug():
            LogUtils.printc(f"[nvidia] manual mode — {model}", color="dim")
        return

    _rotate()

    # Only register hooks if we have models to work with
    if not _models:
        LogUtils.warn("[nvidia] no model data — plugin inactive until /nvidia refresh succeeds")
        ctx.register_command("nvidia", _cmd, "NVIDIA NIM model management")
        return

    ctx.register_hook("before_api_request", _before_request)
    ctx.register_hook("on_api_error", _on_error)
    ctx.register_hook("after_usage_data", _after_usage)
    ctx.register_hook("on_context_bar", _on_context_bar)
    ctx.register_command("nvidia", _cmd, "NVIDIA NIM model management")

    if Config.debug():
        LogUtils.printc(f"[nvidia] auto mode — {_current_model}", color="cyan")


# ── Cache ────────────────────────────────────────────────────────────
def _cache_path():
    return os.path.join(os.getcwd(), ".aicoder", "models.json")


def _load_cache():
    """Load cache if fresh (<1h), otherwise try refresh but keep stale on failure."""
    global _models
    path = _cache_path()
    stale = None

    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            ts = data.get("_ts", 0)
            models = data.get("models", [])
            if time.time() - ts < 3600:
                _models[:] = models
                return              # fresh enough
            stale = models           # hold onto it
        except (json.JSONDecodeError, IOError):
            pass

    # Attempt refresh
    ok = _fetch_models(path)
    if ok:
        return

    # Fetch failed — use stale cache if we have it
    if stale is not None:
        _models[:] = stale
        LogUtils.warn(f"[nvidia] refresh failed, using cached data ({len(stale)} models)")
        return

    # No cache at all — populate from default order so rotation still works
    _models[:] = [{"id": mid, "name": mid.split("/")[-1], "ctx": 0, "out": 0}
                   for mid in _DEFAULT_ORDER]
    LogUtils.warn(f"[nvidia] no cache, using {len(_models)} built-in models")


def _fetch_models(path) -> bool:
    """Fetch from models.dev, write cache on success. Returns True if models loaded."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://models.dev/api.json",
            headers={"User-Agent": "AI-Coder/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = json.loads(r.read().decode())
    except Exception as e:
        LogUtils.warn(f"[nvidia] fetch failed: {e}")
        return False

    nvidia = raw.get("nvidia", {})
    all_m = nvidia.get("models", {}) if isinstance(nvidia, dict) else {}
    filtered = []
    for mid, m in all_m.items():
        if m.get("tool_call") and m.get("reasoning"):
            filtered.append({
                "id": mid,
                "name": m.get("name", mid),
                "ctx": m.get("limit", {}).get("context", 0) if isinstance(m.get("limit"), dict) else 0,
                "out": m.get("limit", {}).get("output", 0) if isinstance(m.get("limit"), dict) else 0,
                "reasoning_options": m.get("reasoning_options", []),
            })

    if not filtered:
        LogUtils.warn("[nvidia] no tool_call+reasoning models in response")
        return False

    filtered.sort(key=lambda x: (-x["ctx"], x["name"]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"_ts": time.time(), "models": filtered}, f, indent=2)
    _models[:] = filtered
    LogUtils.success(f"[nvidia] cached {len(filtered)} models")
    return True


# ── Preference ───────────────────────────────────────────────────────
def _load_preference():
    global _preference
    order = os.environ.get("NVIDIA_NIM_ORDER", "").strip()
    avail = {m["id"] for m in _models}

    if order:
        ids = [x.strip() for x in order.split(",") if x.strip()]
        _preference = [x for x in ids if x in avail] if avail else [x for x in ids]
    else:
        _preference = [x for x in _DEFAULT_ORDER if x in avail] if avail else list(_DEFAULT_ORDER)

    # Append any cache models not in preference
    _preference += [m["id"] for m in _models if m["id"] not in _preference]


# ── Model ops ────────────────────────────────────────────────────────
_EFFORT_PRIORITY = ["max", "xhigh", "high", "medium", "low", "minimal", "none"]
_DEFAULT_EFFORTS = ["none", "low", "medium", "high", "max"]


def _model_data(mid: str) -> Optional[Dict]:
    for m in _models:
        if m["id"] == mid:
            return m
    return None


def _effort_values(mid: str) -> List[str]:
    md = _model_data(mid)
    if not md:
        return _DEFAULT_EFFORTS[:]
    for opt in md.get("reasoning_options", []):
        if isinstance(opt, dict) and opt.get("type") == "effort":
            vals = opt.get("values", [])
            if vals:
                return vals
    return _DEFAULT_EFFORTS[:]


def _best_effort(mid: str) -> str:
    valid = [v.lower() for v in _effort_values(mid)]
    for e in _EFFORT_PRIORITY:
        if e in valid:
            return e
    return valid[0] if valid else "high"


def _fmt(model_id: str) -> str:
    for prefix, fmt in _MODEL_FMT.items():
        if model_id.startswith(prefix):
            return fmt
    return "openai"


def _set_active(mid: str):
    global _current_model
    if not mid or mid == _current_model:
        return
    os.environ["API_MODEL"] = mid
    os.environ["OPENAI_MODEL"] = mid  # Config.model() reads OPENAI_MODEL first
    fmt = _fmt(mid)
    os.environ["REASONING_FORMAT"] = fmt
    Config.set_thinking("on")
    valid = _effort_values(mid)
    os.environ["REASONING_EFFORT_VALID"] = ",".join(valid)
    Config.set_reasoning_effort(_best_effort(mid))
    _current_model = mid
    LogUtils.tip(f"[nvidia] → {mid} (fmt: {fmt}, effort: {valid})")


# ── Reputation ──────────────────────────────────────────────────────
# Base = 100 - preference_index, floor 50.
# Sin pulls below base. Decay restores toward base at +1/min.
# Preference order is always the attractor — forgiveness is automatic over time.
_REP_PATH = os.path.join(os.getcwd(), ".aicoder", "nvidia-rep.json")


def _base(mid: str) -> float:
    """Preference-determined base reputation."""
    try:
        return max(50.0, 100.0 - _preference.index(mid))
    except ValueError:
        return 50.0


def _load_rep():
    _reputation.clear()
    try:
        if os.path.exists(_REP_PATH):
            with open(_REP_PATH) as f:
                data = json.load(f)
            now = time.time()
            for mid, v in data.get("reps", {}).items():
                score = v.get("score", _base(mid))
                ts = v.get("ts", now)
                base = _base(mid)
                if score < base:
                    # Below base — apply recovery
                    recovered = score + (now - ts) * _RECOVERY_RATE / 60
                    _reputation[mid] = min(base, recovered)
                else:
                    # At or above base — preserve as-is (fast bonus)
                    _reputation[mid] = score
                _reputation[f"{mid}_ts"] = ts  # restore timestamp for future decay
    except (json.JSONDecodeError, IOError):
        pass


def _save_rep():
    try:
        os.makedirs(os.path.dirname(_REP_PATH), exist_ok=True)
        with open(_REP_PATH, "w") as f:
            json.dump({
                "reps": {mid: {"score": _reputation.get(mid, _base(mid)),
                               "ts": time.time()}
                         for mid in _preference},
            }, f, indent=2)
    except IOError as e:
        LogUtils.warn(f"[nvidia] failed to save reputation: {e}")


def _rep(mid: str) -> float:
    """Current reputation. Decays toward base on access."""
    with _lock:
        base = _base(mid)
        s = _reputation.get(mid, base)
        if s < base:
            ts = _reputation.get(f"{mid}_ts") or _reputation.get("_ts", time.time())
            s = min(base, s + (time.time() - ts) * _RECOVERY_RATE / 60)
            _reputation[mid] = s
        return s


def _sin(mid: str, points: float):
    """Reduce reputation below base. Floor 0. Recovers naturally."""
    with _lock:
        base = _base(mid)
        curr = _reputation.get(mid, base)
        # decay first
        if curr < base:
            ts = _reputation.get(f"{mid}_ts") or _reputation.get("_ts", time.time())
            curr = min(base, curr + (time.time() - ts) * _RECOVERY_RATE / 60)
        _reputation[mid] = max(0.0, curr - points)
        _reputation[f"{mid}_ts"] = time.time()
    _save_rep()


def _best_model() -> Optional[str]:
    """Model with highest reputation. Preference order breaks ties."""
    best = None
    best_rep = -1
    for mid in _preference:
        s = _rep(mid)
        if s > best_rep:
            best_rep = s
            best = mid
    return best


def _rotate():
    n = _best_model()
    if n:
        _set_active(n)


def _rotate_next():
    """Rotate to next model in preference order after current (for 429 rotation)."""
    global _current_model
    if not _preference or not _current_model:
        _rotate()
        return
    try:
        idx = _preference.index(_current_model)
    except ValueError:
        _rotate()
        return
    for i in range(1, len(_preference)):
        nxt = _preference[(idx + i) % len(_preference)]
        if nxt != _current_model:
            _set_active(nxt)
            return
    # Only one model in preference — stick with it
    _set_active(_preference[0])


# ── Hooks ────────────────────────────────────────────────────────────
def _before_request(endpoint: str, data: dict):
    """Record timing and model for after_usage. No data mutation."""
    global _req_start, _req_model
    _req_start = time.time()
    _req_model = data.get("model", Config.model())


def _on_error(msg: str, status: int):
    mid = _req_model or _current_model or Config.model()
    if not mid:
        return
    try:
        if status == 429:
            _sin(mid, _429_PENALTY)
            LogUtils.warn(f"[nvidia] 429 {mid} — rep -{_429_PENALTY:.0f}")
            _rotate_next()
        elif status == 404:
            _sin(mid, _404_PENALTY)
            LogUtils.warn(f"[nvidia] 404 {mid} — rep -{_404_PENALTY:.0f}")
            _rotate_next()
        elif status in (400, 422):
            _sin(mid, 500)
            LogUtils.warn(f"[nvidia] {status} {mid} — rep -500")
            _rotate_next()
        else:
            pass  # 5xx = transient, don't rotate
    except Exception as e:
        LogUtils.warn(f"[nvidia] _on_error failed: {e}")


def _after_usage(usage: dict):
    """Award reputation for fast responses, sin for slow."""
    completion = usage.get("completion_tokens", 0)
    if completion < 50:
        _rotate()  # still ensure best model is set for next request
        return
    elapsed = time.time() - _req_start
    tok_sec = completion / elapsed if elapsed > 0 else 999
    mid = _req_model
    if tok_sec < 3:
        _sin(mid, _SLOW_PENALTY)
        LogUtils.warn(f"[nvidia] slow {mid}: {tok_sec:.1f} tok/s — rep -{_SLOW_PENALTY:.0f}")
    elif tok_sec > 20:
        base = _base(mid)
        s = _rep(mid)
        if s < base:
            pass  # already decaying toward base naturally
        elif s < base + 5:
            _sin(mid, -_FAST_BONUS)  # small above-base boost
    _rotate()  # ensure best model is active for next request


def _on_context_bar() -> Optional[str]:
    """Hook: append reputation score to context bar."""
    if not _current_model:
        return None
    s = _rep(_current_model)
    return f"score:{s:.0f}"


# ── Commands ─────────────────────────────────────────────────────────
def _cmd(args: str) -> Optional[str]:
    parts = args.strip().split() if args.strip() else []
    if not parts or parts[0] == "status":
        return _status()
    if parts[0] == "list":
        return _list()
    if parts[0] == "set" and len(parts) >= 2:
        return _set(parts[1])
    if parts[0] == "refresh":
        return _refresh()
    if parts[0] == "forgive":
        return _forgive()
    return (
        "Usage:\n"
        "  /nvidia status   - show current state\n"
        "  /nvidia list     - list available models\n"
        "  /nvidia set ID   - force a model\n"
        "  /nvidia refresh  - refresh model cache\n"
        "  /nvidia forgive  - reset all reputations to 100"
    )


def _status() -> str:
    lines = ["[nvidia] Status"]
    lines.append(f"  Base:    {Config.base_url()}")
    lines.append(f"  Current: {_current_model}")
    lines.append(f"  Pref:    {len(_preference)} models")
    lines.append("  Reputation:")
    for mid in _preference:
        s = _rep(mid)
        mark = "←" if mid == _current_model else " "
        base = _base(mid)
        bar = "█" * int(s / 10) + "░" * int((base - s) / 10)
        lines.append(f"    {mark} {mid:<42} {s:5.0f} {bar}")
    return "\n".join(lines)


def _list() -> str:
    if not _models:
        return "[nvidia] no models loaded — try /nvidia refresh"
    lines = ["[nvidia] Available (tool_call + reasoning)"]
    lines.append(f"  {'Model':<45} {'Ctx':>8} {'Out':>7}   Efforts")
    lines.append(f"  {'─' * 45} {'─' * 8} {'─' * 7}   {'─' * 30}")
    for m in _models:
        mid = m["id"]
        ctx = f"{m['ctx']:,}" if m.get("ctx") else "?"
        out = f"{m['out']:,}" if m.get("out") else "?"
        efforts = ",".join(_effort_values(mid))
        marker = "←" if mid == _current_model else " "
        lines.append(f"  {marker}{mid:<44} {ctx:>8} {out:>7}   {efforts}")
    return "\n".join(lines)


def _set(mid: str) -> str:
    match = None
    for m in _models:
        if m["id"] == mid or m["id"].endswith("/" + mid) or mid in m["id"]:
            match = m["id"]
            break
    if not match:
        return f"[nvidia] '{mid}' not found. See /nvidia list"
    _sin(match, 0)  # reset reputation to current (no net change, just freshen)
    _set_active(match)
    return f"[nvidia] → {match}"


def _refresh() -> str:
    path = _cache_path()
    ok = _fetch_models(path)
    if not ok:
        return "[nvidia] refresh failed — see logs for details"
    _load_preference()
    _rotate()
    return f"[nvidia] refreshed — {len(_models)} models"


def _forgive() -> str:
    """Reset all reputations to 100."""
    with _lock:
        _reputation.clear()
    _save_rep()
    LogUtils.success("[nvidia] all reputations reset to 100")
    return "[nvidia] forgiven. All models start clean."
