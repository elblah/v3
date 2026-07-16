"""
NVIDIA NIM Plugin - Smart model rotation for NVIDIA's free API.

Auto-activates when OPENAI_BASE_URL == https://integrate.api.nvidia.com/v1.

Two modes:
  - API_MODEL=auto            → plugin picks best model, auto-rotates on errors
  - API_MODEL=<concrete ID>   → plugin provides /nvidia commands only, no rotation

Features:
  - Maintains ordered preference list of tool_call+reasoning models
  - Detects 429/503 and rotates to next available model
  - 404 penalizes 2x (model deprecated/unavailable)
  - Sticky model: once a model works, hold it for N seconds before testing others
  - Caches filtered NVIDIA model data from models.dev in .aicoder/models.json
  - Stale cache preserved if refresh fails — never lose last good data

Env vars:
  NVIDIA_NIM_ORDER     - comma-separated model ID preference list (default: _DEFAULT_ORDER)
                         Example: NVIDIA_NIM_ORDER="z-ai/glm-5.2,moonshotai/kimi-k2.6,deepseek-ai/deepseek-v4-flash,minimaxai/minimax-m3,minimaxai/minimax-m2.7,stepfun-ai/step-3.7-flash"
  NVIDIA_NIM_STICKY     - seconds to hold a working model before retesting others (default: 420)

Commands:
  /nvidia status   - current model, sticky status, preference
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
# All overridable via env vars (prefix NVIDIA_NIM_)
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(f"NVIDIA_NIM_{name}", str(default)))
    except ValueError:
        return default

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(f"NVIDIA_NIM_{name}", str(default)))
    except ValueError:
        return default

_RECOVERY_RATE = _env_float("RECOVERY_RATE", 2.0)      # rep points recovered per minute toward base
_SLOW_PENALTY = _env_float("SLOW_PENALTY", 10.0)
_TRUST_DECREMENT_SLOW = _env_int("TRUST_DECREMENT_SLOW", 1)  # levels lost per slow response       # rep penalty for <3 tok/s
_429_PENALTY = _env_float("429_PENALTY", 10.0)          # rep penalty for 429
_404_PENALTY = _env_float("404_PENALTY", 20.0)          # rep penalty for 404 (model unavailable/deprecated)
_FAST_BONUS = _env_float("FAST_BONUS", 1.0)             # rep bonus for fast responses
_STICKY_DURATION = _env_int("STICKY", 420)             # seconds to hold a working model
_STICKY_BREAK_TPS = _env_float("STICKY_BREAK_TPS", 1.0)  # tok/s below this breaks sticky

# ── Runtime state ───────────────────────────────────────────────────
NIM_URL = "https://integrate.api.nvidia.com/v1"

_models: List[Dict] = []
_preference: List[str] = []
_reputation: Dict[str, float] = {}  # model_id → score (100=none, lower=sinned)
_current_model: str = ""
_req_start: float = 0.0
_req_model: str = ""
_saved_max_backoff: Optional[int] = None
_strikes: Dict[str, List[float]] = {}  # model_id → [timestamps]
_banned_until: Dict[str, float] = {}  # model_id → unix timestamp
_ban_count: Dict[str, int] = {}       # model_id → consecutive ban count (escalation)
_success_count: Dict[str, int] = {}  # model_id → successful responses
_saved_total_timeout: Optional[int] = None  # saved timeout for untrusted leash
_lock = threading.Lock()
_sticky_until: float = 0              # unix timestamp — next rotation allowed
_current_sticky_model: str = ""       # model that earned the sticky

# Key rotation — multiple API keys to spread 429 limits
_keys: List[str] = []   # available API keys
_key_index: int = 0     # current key index in _keys
_key_tries: int = 0     # consecutive key rotations (reset on success/model switch)

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


# ── Key rotation ─────────────────────────────────────────────────────
def _load_keys():
    global _keys, _key_index
    raw = os.environ.get("NVIDIA_NIM_KEYS", "").strip()
    if not raw:
        return
    _keys = [k.strip() for k in raw.split(",") if k.strip()]
    if _keys:
        _key_index = 0
        os.environ["OPENAI_API_KEY"] = _keys[0]
        LogUtils.warn(f"\n[nvidia] loaded {len(_keys)} API keys")


def _rotate_key() -> bool:
    """Rotate to next key (wraps around). Returns True if rotated, False if all keys tried."""
    if len(_keys) <= 1:
        return False
    global _key_index, _key_tries
    _key_tries += 1
    if _key_tries >= len(_keys):
        return False  # all keys tried in this round
    _key_index = (_key_index + 1) % len(_keys)
    new_key = _keys[_key_index]
    os.environ["OPENAI_API_KEY"] = new_key
    mask = new_key[:8] + "..." if len(new_key) > 8 else new_key
    LogUtils.warn(f"\n[nvidia] key rotated → {_key_index+1}/{len(_keys)} ({mask})")
    return True


def _reset_key():
    """Reset to first key (call when switching models or on success)."""
    if len(_keys) <= 1:
        return
    global _key_index, _key_tries
    _key_index = 0
    _key_tries = 0
    os.environ["OPENAI_API_KEY"] = _keys[0]
    LogUtils.warn(f"\n[nvidia] key reset → 1/{len(_keys)}")


# ── Plugin entry ─────────────────────────────────────────────────────
def create_plugin(ctx):
    base = Config.base_url().rstrip("/")
    if base != NIM_URL:
        return

    _load_cache()
    _load_rep()
    _load_preference()
    _load_bans()
    _load_keys()

    model = Config.model()
    if model != "auto":
        # Manual mode — user chose a specific model, plugin only provides commands
        ctx.register_command("nvidia", _cmd, "NVIDIA NIM model management")
        if Config.debug():
            LogUtils.printc(f"\n[nvidia] manual mode — {model}", color="dim")
        return

    _rotate()

    # Only register hooks if we have models to work with
    if not _models:
        LogUtils.warn("\n[nvidia] no model data — plugin inactive until /nvidia refresh succeeds")
        ctx.register_command("nvidia", _cmd, "NVIDIA NIM model management")
        return

    ctx.register_hook("before_api_request", _before_request)
    ctx.register_hook("on_api_error", _on_error)
    ctx.register_hook("after_usage_data", _after_usage)
    ctx.register_hook("on_empty_assistant_message", _on_empty_response)
    ctx.register_hook("on_context_bar", _on_context_bar)
    ctx.register_command("nvidia", _cmd, "NVIDIA NIM model management")

    if Config.debug():
        LogUtils.printc(f"\n[nvidia] auto mode — {_current_model}", color="cyan")


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
        LogUtils.warn(f"\n[nvidia] refresh failed, using cached data ({len(stale)} models)")
        return

    # No cache at all — populate from default order so rotation still works
    _models[:] = [{"id": mid, "name": mid.split("/")[-1], "ctx": 0, "out": 0}
                   for mid in _DEFAULT_ORDER]
    LogUtils.warn(f"\n[nvidia] no cache, using {len(_models)} built-in models")


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
        LogUtils.warn(f"\n[nvidia] fetch failed: {e}")
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
        LogUtils.warn("\n[nvidia] no tool_call+reasoning models in response")
        return False

    filtered.sort(key=lambda x: (-x["ctx"], x["name"]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"_ts": time.time(), "models": filtered}, f, indent=2)
    _models[:] = filtered
    LogUtils.success(f"\n[nvidia] cached {len(filtered)} models")
    return True


# ── Preference ───────────────────────────────────────────────────────
def _resolve_model(partial: str, avail: set) -> Optional[str]:
    """Resolve partial model ID to full ID: exact → suffix → substring (first match)."""
    if partial in avail:
        return partial
    for mid in avail:
        if mid.endswith("/" + partial):
            return mid
    for mid in avail:
        if partial in mid:
            return mid
    return None


def _resolve_models(partial: str) -> list:
    """Resolve partial model ID to all matching models, sorted by context size desc.
    Exact → matches ending with '/partial' → substring match."""
    matches = []
    for m in _models:
        mid = m["id"]
        if mid == partial:
            return [mid]
        if mid.endswith("/" + partial):
            matches.append(mid)
    if matches:
        matches.sort(key=lambda mid: next((m["ctx"] for m in _models if m["id"] == mid), 0), reverse=True)
        return matches
    for m in _models:
        if partial in m["id"]:
            matches.append(m["id"])
    if matches:
        matches.sort(key=lambda mid: next((m["ctx"] for m in _models if m["id"] == mid), 0), reverse=True)
    return matches


def _load_preference():
    global _preference
    order = os.environ.get("NVIDIA_NIM_ORDER", "").strip()
    avoid_raw = os.environ.get("NVIDIA_NIM_AVOID", "").strip()
    _avoid_patterns = [x.strip().lower() for x in avoid_raw.replace(";", ",").split(",") if x.strip()] if avoid_raw else []
    avail = {m["id"] for m in _models}

    if order:
        ids = [x.strip() for x in order.replace(";", ",").split(",") if x.strip()]
        seen = set()
        _preference = []
        for pid in ids:
            if avail:
                matches = _resolve_models(pid)
                for mid in matches:
                    if mid not in seen:
                        _preference.append(mid)
                        seen.add(mid)
            elif pid not in seen:
                _preference.append(pid)
                seen.add(pid)
    else:
        seen = set()
        _preference = []
        for pid in _DEFAULT_ORDER:
            if avail:
                mid = _resolve_model(pid, avail)
                if mid and mid not in seen:
                    _preference.append(mid)
                    seen.add(mid)
            elif pid not in seen:
                _preference.append(pid)
                seen.add(pid)

    # Append any cache models not in preference
    _preference += [m["id"] for m in _models if m["id"] not in _preference]

    # Filter out avoided models
    if _avoid_patterns:
        def _is_avoided(mid: str) -> bool:
            ml = mid.lower()
            return any(p in ml for p in _avoid_patterns)
        before = len(_preference)
        _preference[:] = [m for m in _preference if not _is_avoided(m)]
        removed = before - len(_preference)
        if removed:
            LogUtils.warn(f"\n[nvidia] NVIDIA_NIM_AVOID: filtered {removed} models")


# ── Model ops ────────────────────────────────────────────────────────
_EFFORT_PRIORITY = ["max", "xhigh", "high", "medium", "low", "minimal", "none"]
_DEFAULT_EFFORTS = ["none", "low", "medium", "high", "max"]


def _model_data(mid: str) -> Optional[Dict]:
    for m in _models:
        if m["id"] == mid:
            return m
    return None


def _effort_values(mid: str) -> Optional[List[str]]:
    """Returns effort value list, or None if model doesn't support effort control."""
    md = _model_data(mid)
    if not md:
        return _DEFAULT_EFFORTS[:]
    opts = md.get("reasoning_options", [])
    for opt in opts:
        if isinstance(opt, dict) and opt.get("type") == "effort":
            vals = opt.get("values", [])
            if vals:
                return vals
            return None  # effort type declared but empty values
    # toggle or empty — no effort control
    return None


def _best_effort(mid: str) -> Optional[str]:
    """Returns best effort value, or None if model doesn't support effort."""
    effort_list = _effort_values(mid)
    if effort_list is None:
        return None
    valid = [v.lower() for v in effort_list]
    for e in _EFFORT_PRIORITY:
        if e in valid:
            return e
    return valid[0] if valid else None


def _fmt(model_id: str) -> str:
    for prefix, fmt in _MODEL_FMT.items():
        if model_id.startswith(prefix):
            return fmt
    return "openai"


def _set_active(mid: str):
    global _current_model
    if not mid or mid == _current_model:
        return
    _reset_key()
    os.environ["API_MODEL"] = mid
    os.environ["OPENAI_MODEL"] = mid  # Config.model() reads OPENAI_MODEL first
    fmt = _fmt(mid)
    os.environ["REASONING_FORMAT"] = fmt
    Config.set_thinking("on")
    effort = _best_effort(mid)
    if effort:
        os.environ["REASONING_EFFORT_VALID"] = ",".join(_effort_values(mid) or [])
        Config.set_reasoning_effort(effort)
    else:
        os.environ["REASONING_EFFORT_VALID"] = ""
        Config.set_reasoning_effort(None)
    _current_model = mid
    LogUtils.tip(f"\n[nvidia] → {mid} (fmt: {fmt}, effort: {effort or 'toggle'})\n")


# ── Reputation ──────────────────────────────────────────────────────
# Base = 100 - preference_index, floor 50.
# Sin pulls below base. Decay restores toward base at +1/min.
# Preference order is always the attractor — forgiveness is automatic over time.
_REP_PATH = os.path.join(os.getcwd(), ".aicoder", "nvidia-rep.json")
_BANS_PATH = os.path.join(os.getcwd(), ".aicoder", "nvidia-bans.json")


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
        LogUtils.warn(f"\n[nvidia] failed to save reputation: {e}")


def _load_bans():
    try:
        if os.path.exists(_BANS_PATH):
            with open(_BANS_PATH) as f:
                data = json.load(f)
            _strikes.clear()
            _banned_until.clear()
            _ban_count.clear()
            for mid, strikes in data.get("strikes", {}).items():
                _strikes[mid] = [t for t in strikes if time.time() - t < 7200]
            for mid, until in data.get("banned_until", {}).items():
                if time.time() < until:
                    _banned_until[mid] = until
            for mid, cnt in data.get("ban_count", {}).items():
                _ban_count[mid] = cnt
    except (json.JSONDecodeError, IOError):
        pass


def _save_bans():
    try:
        os.makedirs(os.path.dirname(_BANS_PATH), exist_ok=True)
        clean_strikes = {mid: ts for mid, ts in _strikes.items() if ts}
        with open(_BANS_PATH, "w") as f:
            json.dump({
                "strikes": clean_strikes,
                "banned_until": _banned_until,
                "ban_count": _ban_count,
            }, f, indent=2)
    except IOError as e:
        LogUtils.warn(f"\n[nvidia] failed to save bans: {e}")


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
    """Model with highest reputation. Skips banned models unless all banned."""
    best = None
    best_rep = -1
    best_banned = None
    best_ban = float("inf")
    now = time.time()
    for mid in _preference:
        banned_until = _banned_until.get(mid, 0)
        if now < banned_until:
            if banned_until < best_ban:
                best_ban = banned_until
                best_banned = mid
            continue
        s = _rep(mid)
        if s > best_rep:
            best_rep = s
            best = mid
    # All models banned — return the one with soonest-expiring ban
    if best is None:
        best = best_banned
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
    now = time.time()
    for i in range(1, len(_preference)):
        nxt = _preference[(idx + i) % len(_preference)]
        if nxt != _current_model and now >= _banned_until.get(nxt, 0):
            _set_active(nxt)
            return
    # All others banned — use best available (including earliest-expiring banned)
    _set_active(_best_model() or _preference[0])


# ── Hooks ────────────────────────────────────────────────────────────
def _is_timeout(msg: str) -> bool:
    """True if error message indicates a timeout (no response from model)."""
    low = msg.lower()
    return "timeout" in low or "timed out" in low or "timedout" in low or "time out" in low


_STRIKE_WINDOW = _env_int("STRIKE_WINDOW", 7200)      # 2h — strikes older than this are ignored
_STRIKE_LIMIT = _env_int("STRIKE_LIMIT", 3)           # strikes within window → ban
_BAN_DURATION = _env_int("BAN_DURATION", 86400)       # 24h (manual /avoid)
_BAN_DURATION_404 = _env_int("BAN_DURATION_404_MIN", 60) * 60   # 404: model not found, may come back
_BAN_DURATION_SLOW = _env_int("BAN_DURATION_SLOW_MIN", 30) * 60 # slow: model degraded, may recover
_BAN_DURATION_ESCALATE = _env_int("BAN_DURATION_ESCALATE_MIN", 15) * 60  # base for escalating bans
_BAN_DURATION_MAX = _env_int("BAN_DURATION_MAX_MIN", 480) * 60  # cap for escalated bans (8h)
_TRUST_THRESHOLD = _env_int("TRUST_THRESHOLD", 8)     # successes to be considered trusted
_TRUST_LEVEL_CAP = _env_int("TRUST_LEVEL_CAP", 5)      # max trust level
_TRUST_LEVEL_MINUTES = _env_int("TRUST_LEVEL_MINUTES", 1)  # minutes per trust level


def _strike(mid: str):
    """Record a timeout strike. 3 strikes → escalating ban."""
    now = time.time()
    with _lock:
        strikes = [t for t in _strikes.get(mid, []) if now - t < _STRIKE_WINDOW]
        strikes.append(now)
        _strikes[mid] = strikes
        count = len(strikes)
        if count >= _STRIKE_LIMIT:
            # Escalate: base * 2^(ban_count-1), cap at _BAN_DURATION_MAX
            bc = _ban_count.get(mid, 0)
            duration = min(_BAN_DURATION_ESCALATE * (2 ** bc), _BAN_DURATION_MAX)
            _banned_until[mid] = now + duration
            _strikes[mid] = []
            _ban_count[mid] = bc + 1
            LogUtils.warn(f"\n[nvidia] {mid} — {count} strikes → banned for {duration // 60}m (ban #{bc + 1})")
        else:
            LogUtils.warn(f"\n[nvidia] {mid} — timeout strike {count}/{_STRIKE_LIMIT}")
    _save_bans()


def _before_request(endpoint: str, data: dict):
    """Record timing and model for after_usage. No data mutation."""
    global _req_start, _req_model, _saved_total_timeout
    _req_start = time.time()
    _req_model = data.get("model", Config.model())

    # Trust-level based timeout: level 1 → 1 min, level 5 → 5 min cap
    # Level = successful responses + 1 (starts at 1 minute)
    mid = _req_model
    if mid:
        level = _success_count.get(mid, 0)
        timeout_min = min(level, _TRUST_LEVEL_CAP - 1) + 1
        timeout_sec = timeout_min * _TRUST_LEVEL_MINUTES * 60
        if _saved_total_timeout is None:
            _saved_total_timeout = Config.total_timeout()
        Config.set_runtime_total_timeout(timeout_sec)


_EMPTY_RESPONSE_PENALTY = int(os.environ.get("NIM_EMPTY_RESPONSE_PENALTY", "3"))

def _on_empty_response():
    """Model returned empty response — break sticky, rotate, reset trust level."""
    mid = _req_model or _current_model or Config.model()
    if not mid:
        return
    global _sticky_until, _current_sticky_model
    _sticky_until = 0
    _current_sticky_model = ""
    _success_count[mid] = 0
    _sin(mid, _EMPTY_RESPONSE_PENALTY)
    _rotate_next()
    LogUtils.warn(f"\n[nvidia] empty response from {mid} — trust→1, rotated")


def _on_error(msg: str, status: int):
    mid = _req_model or _current_model or Config.model()
    if not mid:
        return
    # Error breaks sticky — let rotation find a working model
    global _sticky_until, _current_sticky_model
    _sticky_until = 0
    _current_sticky_model = ""
    rotated = False
    try:
        if status == 429:
            _sin(mid, _429_PENALTY)
            LogUtils.warn(f"\n[nvidia] 429 {mid} — rep -{_429_PENALTY:.0f}")
            if _rotate_key():
                LogUtils.warn(f"\n[nvidia] retrying {mid} with next key")
            else:
                LogUtils.warn(f"\n[nvidia] all {len(_keys)} keys exhausted for {mid} — rotating model")
                _rotate_next()
                rotated = True
        elif status == 404:
            _sin(mid, _404_PENALTY)
            _banned_until[mid] = time.time() + _BAN_DURATION_404
            _strikes[mid] = []
            _save_bans()
            LogUtils.warn(f"\n[nvidia] 404 {mid} — banned {_BAN_DURATION_404 // 60}m (model unavailable)")
            _rotate_next()
            rotated = True
        elif status == 503:
            _sin(mid, _429_PENALTY)
            LogUtils.warn(f"\n[nvidia] 503 {mid} — rep -{_429_PENALTY:.0f}")
            _rotate_next()
            rotated = True
        elif status in (400, 422):
            ml = (msg or "").lower()
            if "degraded" in ml or "function" in ml:
                # Permanent model failure — ban like 404
                _sin(mid, _404_PENALTY)
                _banned_until[mid] = time.time() + _BAN_DURATION_404
                _strikes[mid] = []
                _save_bans()
                LogUtils.warn(f"\n[nvidia] {status} {mid} — degraded/function ban {_BAN_DURATION_404 // 60}m")
            else:
                _sin(mid, _429_PENALTY)
                LogUtils.warn(f"\n[nvidia] {status} {mid} — rep -{_429_PENALTY:.0f}")
            _rotate_next()
            rotated = True
        elif status == 0 and _is_timeout(msg):
            # Model is slow (not broken) — rotate, light rep nudge, no strike
            # Reset trust level — model couldn't deliver in its time window
            _success_count[mid] = 0
            _sin(mid, 2)
            LogUtils.warn(f"\n[nvidia] timeout {mid} — rep -2, trust→1, rotated")
            _rotate_next()
            rotated = True
        else:
            pass  # other 5xx = transient, don't rotate
    except Exception as e:
        LogUtils.warn(f"\n[nvidia] _on_error failed: {e}")
    if rotated:
        global _saved_max_backoff
        if _saved_max_backoff is None:
            _saved_max_backoff = Config.effective_max_backoff()
        Config.set_runtime_max_backoff(2)


def _after_usage(usage: dict):
    """Award reputation for fast responses, sin for slow."""
    global _saved_max_backoff, _saved_total_timeout, _sticky_until, _current_sticky_model, _key_tries
    if _saved_max_backoff is not None:
        Config.set_runtime_max_backoff(_saved_max_backoff)
        _saved_max_backoff = None
    if _saved_total_timeout is not None:
        Config.set_runtime_total_timeout(_saved_total_timeout)
        _saved_total_timeout = None

    # Reset key rotation tracking on successful response
    _key_tries = 0

    mid = _req_model
    completion = usage.get("completion_tokens", 0)

    # Trust: model responded with meaningful output
    elapsed = time.time() - _req_start
    tok_sec = completion / elapsed if elapsed > 0 else 999
    mid = _req_model
    # tok/s meaningless for short responses — latency dominates
    if completion >= 20 and tok_sec < 3:
        _sin(mid, _SLOW_PENALTY)
        if tok_sec < _STICKY_BREAK_TPS:
            # Severe: model is crawling — full trust reset, break sticky, ban, rotate
            _success_count[mid] = 0
            LogUtils.warn(f"\n[nvidia] slow {mid}: {tok_sec:.1f} tok/s — rep -{_SLOW_PENALTY:.0f}, trust→1")
            if _current_sticky_model == _current_model:
                _sticky_until = 0
                _current_sticky_model = ""
                LogUtils.warn(f"\n[nvidia] sticky broken — {mid} too slow ({tok_sec:.1f} < {_STICKY_BREAK_TPS:.1f} t/s)")
            _banned_until[mid] = time.time() + _BAN_DURATION_SLOW
            _save_bans()
            _rotate_next()
        else:
            # Moderate: model is functional but slow — decrement trust, no ban, no rotate
            prev = _success_count.get(mid, 0)
            new_level = max(0, prev - _TRUST_DECREMENT_SLOW)
            _success_count[mid] = new_level
            LogUtils.warn(f"\n[nvidia] slow {mid}: {tok_sec:.1f} tok/s — rep -{_SLOW_PENALTY:.0f}, trust {prev}→{new_level}")
    elif mid:
        prev = _success_count.get(mid, 0)
        _success_count[mid] = prev + 1
        if prev < _TRUST_THRESHOLD and prev + 1 >= _TRUST_THRESHOLD:
            LogUtils.success(f"\n[nvidia] {mid} — trusted ({prev + 1} responses)")
            _ban_count.pop(mid, None)  # reset escalation — model proven good
            _save_bans()
        if completion >= 20 and tok_sec > 20:
            base = _base(mid)
            s = _rep(mid)
            if s < base:
                pass  # already decaying toward base naturally
            elif s < base + 5:
                _sin(mid, -_FAST_BONUS)  # small above-base boost

    # Sticky: once a model produces good output, hold it for _STICKY_DURATION
    if mid and completion >= 50 and tok_sec >= 3:
        _sticky_until = time.time() + _STICKY_DURATION
        _current_sticky_model = _current_model


def _on_context_bar() -> Optional[str]:
    """Hook: append reputation score to context bar."""
    if not _current_model:
        return None
    s = _rep(_current_model)
    if len(_keys) > 1:
        return f"score:{s:.0f} ({_key_index+1}/{len(_keys)})"
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
    if parts[0] in ("forgive", "F"):
        return _forgive()
    if parts[0] == "avoid":
        return _avoid(parts[1] if len(parts) > 1 else "")
    if parts[0] == "unban":
        return _unban(parts[1] if len(parts) > 1 else "")
    if parts[0] == "bans":
        return _show_bans()
    return (
        "Usage:\n"
        "  /nvidia status   - show current state\n"
        "  /nvidia list     - list available models\n"
        "  /nvidia set ID   - force a model\n"
        "  /nvidia refresh  - refresh model cache\n"
        "  /nvidia forgive  - reset reputations + clear bans (alias: F)\n"
        "  /nvidia avoid [M]- 24h ban for model (current if omitted)\n"
        "  /nvidia unban M  - remove ban + strikes for model\n"
        "  /nvidia bans     - show banned/striked models"
    )


def _status() -> str:
    lines = ["[nvidia] Status"]
    lines.append(f"  Base:    {Config.base_url()}")
    lines.append(f"  Current: {_current_model}")
    if _keys:
        key_label = _keys[_key_index][:8] + "..." if len(_keys[_key_index]) > 8 else _keys[_key_index]
        lines.append(f"  Key:     {_key_index+1}/{len(_keys)} ({key_label})")
    if _current_sticky_model and time.time() < _sticky_until:
        rem = _sticky_until - time.time()
        lines.append(f"  Sticky:  {_current_sticky_model} (remaining: {rem:.0f}s)")
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
        efforts = ",".join(_effort_values(mid) or []) or "toggle"
        marker = "←" if mid == _current_model else " "
        lines.append(f"  {marker}{mid:<44} {ctx:>8} {out:>7}   {efforts}")
    return "\n".join(lines)


def _set(mid: str) -> str:
    avail = {m["id"] for m in _models}
    match = _resolve_model(mid, avail)
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
    """Reset all reputations to 100 and clear all bans."""
    with _lock:
        _reputation.clear()
        _strikes.clear()
        _banned_until.clear()
        _ban_count.clear()
        _success_count.clear()
    _save_rep()
    _save_bans()
    LogUtils.success("\n[nvidia] all reputations reset, bans cleared")
    return "[nvidia] forgiven. All models start clean."


def _avoid(mid: str) -> str:
    """Manual 24h ban. If no model given, bans current."""
    if not mid:
        mid = _current_model
    if not mid:
        return "[nvidia] no model to avoid"
    if mid not in _preference:
        return f"[nvidia] '{mid}' not in model list"
    _banned_until[mid] = time.time() + _BAN_DURATION
    _strikes.pop(mid, None)
    _save_bans()
    LogUtils.warn(f"\n[nvidia] {mid} — avoided for 24h")
    if mid == _current_model:
        _rotate_next()
    return f"[nvidia] avoided {mid} for 24h"


def _unban(mid: str) -> str:
    """Remove ban and strikes for a model."""
    if not mid:
        return "[nvidia] specify model to unban"
    if mid not in _preference:
        return f"[nvidia] '{mid}' not in model list"
    _banned_until.pop(mid, None)
    _strikes.pop(mid, None)
    _save_bans()
    LogUtils.success(f"\n[nvidia] {mid} — ban removed")
    return f"[nvidia] unbanned {mid}"


def _show_bans() -> str:
    """Show banned models and strikes."""
    now = time.time()
    lines = ["[nvidia] Bans & Strikes"]
    has_any = False
    for mid in _preference:
        until = _banned_until.get(mid, 0)
        strikes = len([t for t in _strikes.get(mid, []) if now - t < _STRIKE_WINDOW])
        bc = _ban_count.get(mid, 0)
        if until > now:
            remaining = until - now
            h = int(remaining // 3600)
            m = int((remaining % 3600) // 60)
            bc_str = f" (ban #{bc})" if bc else ""
            lines.append(f"  {mid} — banned ({h}h{m:02d}m remaining){bc_str}")
            has_any = True
        elif strikes:
            bc_str = f" (ban #{bc})" if bc else ""
            lines.append(f"  {mid} — {strikes} strike(s){bc_str}")
            has_any = True
    if not has_any:
        lines.append("  (none)")
    return "\n".join(lines)
