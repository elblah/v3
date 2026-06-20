#!/usr/bin/env python3
"""AI Usage Statistics Reporter.

Finds all .aicoder/stats.log files and aggregates usage statistics.
Uses a persistent cache (no expiration). Run `update` to refresh cache.

Usage:
    python ai_usage.py [today|yesterday|24h|week|month|year] # Preset periods
    python ai_usage.py hours <N> | days <N> | minutes <N>    # Custom durations
    python ai_usage.py YYYY-MM-DD YYYY-MM-DD                 # Date range
    python ai_usage.py update                                # Scan & update cache
    python ai_usage.py clear-cache                           # Delete cache
    python ai_usage.py help                                  # Show this usage
    ALL=1 python ai_usage.py ...                             # Global stats (ignore cwd)
    CENTRAL=1 python ai_usage.py ...                         # Use central log

Notes:
    - Cache persists indefinitely. Run 'update' to scan all dirs below PWD.
    - Default period is 24h (rolling).
    - Stats are loaded from central log (~/.aicoder/central_stats.log) by default.
    - LOCAL=1 uses per-project .aicoder/stats.log instead.
    - TZ=+8 sets timezone offset (useful for matching provider dashboards).

Cache behavior:
    - Cache persists indefinitely (no automatic expiration)
    - --update scans all dirs below, adds new entries, removes invalid ones
    - Normal runs filter cached dirs to current $PWD (must have stats.log).
    - ALL=1 shows stats from ALL cached dirs regardless of cwd.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
try:
    import orjson
    json_loads = orjson.loads
except ImportError:
    json_loads = json.loads
import os
from pathlib import Path
from typing import List, Dict, Any

CACHE_FILE = Path.home() / ".cache" / "ai_usage_dirs_cache.txt"
FILTER_TAG = os.environ.get("FILTER_TAG")


def parse_usage(usage: Dict[str, Any], provider: str) -> Dict[str, int]:
    """Extract prompt, completion, cache_read, cache_miss, cost from raw usage object.

    Returns dict with: prompt, completion, cache_read, cache_miss, cost

    IMPORTANT: Providers define "input_tokens" differently:
    - Anthropic: input_tokens = NON-CACHED only (cache miss). Total = input_tokens + cache_read_input_tokens
    - OpenAI:    prompt_tokens = TOTAL input (cached + non-cached). Miss = prompt_tokens - cached_tokens

    This is NOT a bug. Each provider has different semantics for what counts as "input".
    """
    if provider == "anthropic":
        # Anthropic raw usage fields:
        #   input_tokens               = tokens NOT in cache (cache miss, paid at full price)
        #   cache_read_input_tokens    = tokens read from cache (cache hit, discounted)
        #   cache_creation_input_tokens = tokens written to cache (one-time write cost)
        #   output_tokens              = generated tokens
        #
        # Total input = input_tokens + cache_read_input_tokens
        # We store input_tokens as cache_miss since it represents non-cached tokens.
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0
        cache_read = usage.get("cache_read_input_tokens") or 0
        prompt = input_tokens + cache_read
        return {
            "prompt": prompt,      # Total input (cached + non-cached)
            "completion": output_tokens,
            "cache_read": cache_read,
            "cache_miss": input_tokens,  # Same as input_tokens for Anthropic
            "cost": 0,
        }
    else:
        # OpenAI raw usage fields:
        #   prompt_tokens                    = TOTAL input tokens (cached + non-cached)
        #   prompt_tokens_details.cached_tokens = tokens read from cache (cache hit)
        #   completion_tokens                = generated tokens
        #
        # Cached tokens are INCLUDED in prompt_tokens, not separate.
        # To get non-cached (miss): prompt_tokens - cached_tokens
        prompt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        prompt_details = usage.get("prompt_tokens_details") or {}
        # Try OpenAI field first, then OpenAI-compatible providers using Anthropic-style names
        cache_read = (prompt_details.get("cached_tokens")
                     or usage.get("cache_read_input_tokens")
                     or usage.get("prompt_cache_hit_tokens") or 0)
        # prompt_tokens already includes cached, so subtract to get miss
        cache_miss = max(0, prompt - cache_read) if cache_read > 0 else prompt
        cost = (usage.get("cost_details", {}).get("upstream_inference_cost")
               or usage.get("cost") or 0)
        return {
            "prompt": prompt,      # Total input (cached + non-cached)
            "completion": completion,
            "cache_read": cache_read,
            "cache_miss": cache_miss,
            "cost": cost,
        }


def get_cache_file() -> Path:
    """Ensure cache directory exists, return cache file path."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return CACHE_FILE


def read_cache() -> List[Path]:
    """Read all cached project directories (no expiration)."""
    if not CACHE_FILE.exists():
        return []
    try:
        paths = []
        for line in CACHE_FILE.read_text().splitlines():
            if line.strip():
                paths.append(Path(line.strip()))
        return paths
    except (OSError, IOError):
        return []


def write_cache(paths: List[Path]) -> None:
    """Write project directories to cache."""
    try:
        cache = get_cache_file()
        cache.write_text("\n".join(str(p) for p in paths) + "\n")
    except (OSError, IOError):
        pass


def clear_cache() -> None:
    """Delete cache file if exists."""
    if CACHE_FILE.exists():
        try:
            CACHE_FILE.unlink()
        except (OSError, IOError):
            pass


def update_cache() -> List[Path]:
    """Scan filesystem, add new project dirs, remove invalid ones, return all valid dirs."""
    print("Scanning for .aicoder/stats.log files...", flush=True)

    # Find all stats.log files and get their GRANDPARENT directories (project dirs)
    files = list(Path(".").rglob(".aicoder/stats.log"))
    # stats.log is in .aicoder which is in project dir, so go up 2 levels
    found_dirs = set(f.parent.parent.resolve() for f in files)  # e.g., /home/blah/poc

    # Read existing cache
    existing_cache = read_cache()

    # Convert to project dirs (handle old cache formats)
    existing_proj_dirs = set()
    for p in existing_cache:
        if p.name == "stats.log":
            # /proj/.aicoder/stats.log -> /proj
            existing_proj_dirs.add(p.parent.parent.resolve())
        elif p.name == ".aicoder":
            # /proj/.aicoder -> /proj
            existing_proj_dirs.add(p.parent.resolve())
        else:
            # /proj (already project dir)
            existing_proj_dirs.add(p.resolve())

    # Validate: keep only dirs that still exist and have stats.log
    valid_existing = [d for d in existing_proj_dirs if d.exists() and (d / ".aicoder" / "stats.log").exists()]

    # Merge: keep valid existing + newly found
    all_dirs = list(set(valid_existing) | found_dirs)
    all_dirs.sort(key=str)

    # Write back
    if all_dirs:
        write_cache(all_dirs)

    print(f"Cache updated: {len(found_dirs)} found, {len(valid_existing)} valid from cache, {len(all_dirs)} total.", flush=True)
    return all_dirs


def find_stats_files() -> List[Path]:
    """Read cache (project dirs), filter by current PWD, return stats.log paths."""
    cached_dirs = read_cache()
    if not cached_dirs:
        print("Cache is empty. Run with --update to scan.", flush=True)
        return []

    cwd = Path.cwd().resolve()

    # Convert cached paths to project directories (handle all old formats)
    project_dirs = set()
    for p in cached_dirs:
        if p.name == "stats.log":
            # /proj/.aicoder/stats.log -> /proj
            proj = p.parent.parent
        elif p.name == ".aicoder":
            # /proj/.aicoder -> /proj
            proj = p.parent
        else:
            # /proj (already project dir)
            proj = p
        project_dirs.add(proj.resolve())

    # Filter: only project dirs in/below current PWD, unless ALL=1
    show_all = bool(os.environ.get("ALL"))
    files = []
    for d in project_dirs:
        if not show_all:
            try:
                d.relative_to(cwd)
            except ValueError:
                continue
        stats_file = d / ".aicoder" / "stats.log"
        if stats_file.exists():
            files.append(stats_file)

    return files


def _get_tz_offset() -> timedelta:
    """Parse TZ env var (e.g. '+8', '-5', '+5:30') into timedelta offset from UTC."""
    tz = os.environ.get("TZ", "")
    if not tz:
        return timedelta(0)
    # Handle format like "+8", "-5", "+5:30", "+08:00"
    sign = 1 if tz.startswith("+") else -1 if tz.startswith("-") else 0
    if sign == 0:
        return timedelta(0)
    tz = tz[1:]  # strip sign
    parts = tz.split(":")
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0
    return timedelta(hours=hours, minutes=minutes) * sign


def get_time_range(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) datetime for a period in local timezone (set via TZ env var)."""
    tz_offset = _get_tz_offset()
    now = (datetime.now(timezone.utc) + tz_offset).replace(tzinfo=None)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        return (today_midnight, now)
    elif period == "yesterday":
        yesterday_midnight = today_midnight - timedelta(days=1)
        return (yesterday_midnight, today_midnight)
    else:
        delta = {
            "24h": timedelta(days=1),
            "week": timedelta(weeks=1),
            "month": timedelta(days=30),
            "year": timedelta(days=365),
        }.get(period)
        return (now - delta, now) if delta else (None, None)


def _parse_line(line: str, start: datetime | None, end: datetime | None) -> dict | None:
    """Parse a single JSONL stats.log line."""
    if not line or not line.startswith("{"):
        return None

    try:
        entry = json_loads(line)
        # Filter by tag if FILTER_TAG env var is set
        if FILTER_TAG is not None:
            entry_tag = entry.get("tag")
            if FILTER_TAG == "":
                # Match entries with no tag or empty tag
                if entry_tag:
                    return None
            elif entry_tag != FILTER_TAG:
                return None
        ts = entry["ts"].replace("_", "T")
        dt = datetime.fromisoformat(ts)
        # Log timestamps are UTC; convert to local time for comparison
        dt = dt + _get_tz_offset()
        if start and (dt < start or dt > end):
            return None
        provider = entry.get("api_provider", "openai")
        usage = entry.get("usage", {})
        parsed = parse_usage(usage, provider)
        return {
            "url": entry.get("url", ""),
            "model": entry.get("model", ""),
            "session": entry.get("session", ""),
            "prompt": parsed["prompt"],
            "completion": parsed["completion"],
            "elapsed": entry.get("elapsed", 0),
            "cache_read": parsed["cache_read"],
            "cache_miss": parsed["cache_miss"],
            "cost": parsed["cost"],
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def parse_stats(filepath: Path, start: datetime | None, end: datetime | None) -> List[Dict]:
    """Parse a stats.log file, return entries within time range."""
    entries = []
    for line in filepath.read_text().splitlines():
        entry = _parse_line(line, start, end)
        if entry:
            entries.append(entry)
    return entries


def parse_central_stats(filepath: Path, start: datetime | None, end: datetime | None) -> List[Dict]:
    """Parse central_stats.log, return entries within time range."""
    if not filepath.exists():
        return []
    return parse_stats(filepath, start, end)


def main():
    import sys
    args = sys.argv[1:]

    # Handle manual cache commands
    if "clear-cache" in args:
        clear_cache()
        print("Cache cleared.")
        sys.exit(0)
    elif "--help" in args or "-h" in args or "help" in args:
        print("Usage:")
        print("  ai_usage.py [today|yesterday|24h|week|month|year]         # Time period")
        print("  ai_usage.py hours <N> | days <N> | minutes <N>           # Custom periods")
        print("  ai_usage.py YYYY-MM-DD YYYY-MM-DD                        # Date range")
        print("  ai_usage.py update         # Scan all dirs below, update cache")
        print("  ai_usage.py clear-cache    # Delete cache")
        print("  ALL=1 ai_usage.py ...      # All cached dirs (ignore cwd filter)")
        sys.exit(0)
    elif "update" in args:
        # Update cache: scan filesystem, add new dirs, remove invalid
        update_cache()
        sys.exit(0)

    # Parse time range
    if len(args) >= 2 and args[0] in ("hours", "days", "minutes"):
        try:
            if args[0] == "hours":
                # Support hours:minutes format (e.g., "4:20" = 4h 20m)
                if ':' in args[1]:
                    parts = args[1].split(':')
                    delta = timedelta(hours=int(parts[0]), minutes=int(parts[1]))
                    label = f"last {parts[0]}h {parts[1]}m"
                else:
                    delta = timedelta(hours=int(args[1]))
                    label = f"last {args[1]} hours"
            elif args[0] == "days":
                delta = timedelta(days=int(args[1]))
                label = f"last {args[1]} days"
            else:
                delta = timedelta(minutes=int(args[1]))
                label = f"last {args[1]} minutes"
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            start = now - delta
            end = now
        except ValueError:
            print(f"Error: Invalid number '{args[1]}'")
            sys.exit(1)
    elif len(args) >= 2 and "-" in args[0]:
        try:
            start = datetime.strptime(args[0], "%Y-%m-%d")
            end = datetime.strptime(args[1], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            label = f"{args[0]} to {args[1]}"
        except ValueError:
            print("Error: Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        period = args[0] if args else "24h"
        start, end = get_time_range(period)
        if not start:
            print(f"Error: Unknown period '{period}'")
            print("Usage: ai_usage.py [today|yesterday|24h|week|month|year|minutes <N>|hours <N>|days <N>|<start_date> <end_date>]")
            sys.exit(1)
        label = period

    # Find and parse stats files
    if os.environ.get("LOCAL"):
        files = find_stats_files()
        if not files:
            print("No .aicoder/stats.log files found.")
            sys.exit(0)
        entries = [e for f in files for e in parse_stats(f, start, end)]
        if not entries:
            print(f"No requests found for: {label}")
            sys.exit(0)
    else:
        central_path = Path.home() / ".aicoder" / "central_stats.log"
        print(f"Using central log: {central_path}")
        entries = parse_central_stats(central_path, start, end)
        if not entries:
            print(f"No requests found in central log for: {label}")
            sys.exit(0)

    # Aggregate: url -> model -> stats
    agg: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "p": 0, "c": 0, "t": 0.0, "cr": 0, "cm": 0, "cost": 0.0}))
    for e in entries:
        if e["model"] == "test-model":
            continue
        agg[e["url"]][e["model"]]["n"] += 1
        agg[e["url"]][e["model"]]["p"] += e["prompt"]
        agg[e["url"]][e["model"]]["c"] += e["completion"]
        agg[e["url"]][e["model"]]["t"] += e["elapsed"]
        agg[e["url"]][e["model"]]["cr"] += e.get("cache_read", 0)
        agg[e["url"]][e["model"]]["cm"] += e.get("cache_miss", 0)
        cost = e.get("cost", 0.0)
        if isinstance(cost, dict):
            cost = cost.get("usd", 0.0)
        agg[e["url"]][e["model"]]["cost"] += cost

    # Report
    print(f"\n{'='*60}")
    print(f"  AI Usage Report: {label}")
    print(f"{'='*60}")
    if start and end:
        tz_name = os.environ.get("TZ", "UTC")
        now = (datetime.now(timezone.utc) + _get_tz_offset()).replace(tzinfo=None)
        print(f"  Now:      {now.strftime('%Y-%m-%d %H:%M:%S')} (TZ={tz_name})")
        print(f"  Range:    {start.strftime('%Y-%m-%d %H:%M:%S')} → {end.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
    total = {"n": 0, "p": 0, "c": 0, "t": 0.0, "cr": 0, "cm": 0, "cost": 0.0}

    for url in sorted(agg):
        print(url)
        for model in sorted(agg[url]):
            d = agg[url][model]
            avg = d["t"] / d["n"]
            toks = d["c"]  # output tokens only for generation speed
            tps = toks / d["t"] if d["t"] > 0 else 0
            # Cache percentages per model
            total_input = d['cr'] + d['cm']
            pct_hit = d['cr'] / total_input * 100 if total_input else 0
            pct_miss = d['cm'] / total_input * 100 if total_input else 0
            print(f"    Model: {model}")
            print(f"        Requests:       {d['n']:,}")
            print(f"        Input Tokens:   {d['p']:,}")
            print(f"        Output Tokens:  {d['c']:,}")
            print(f"        Cache Hit:      {d['cr']:,} ({pct_hit:.1f}%)")
            print(f"        Cache Miss:     {d['cm']:,} ({pct_miss:.1f}%)")
            if d["cost"] > 0:
                print(f"        Cost:           ${d['cost']:.6f}")
            print(f"        Avg Req Time:   {avg:.2f}s")
            print(f"        Output tok/s:   {tps:.1f}\n")
            total["n"] += d["n"]
            total["p"] += d["p"]
            total["c"] += d["c"]
            total["t"] += d["t"]
            total["cr"] += d["cr"]
            total["cm"] += d["cm"]
            total["cost"] += d["cost"]

    n = total["n"]
    # Number of days in range for per-day averages
    day_secs = (end - start).total_seconds() / 86400 if start and end and end > start else 1
    print("-" * 50)
    print("TOTAL SUMMARY")
    print(f"    Total Requests:      {total['n']:,}")
    print(f"    Total Input Tokens:  {total['p']:,}")
    print(f"    Total Output Tokens: {total['c']:,}")
    pct_hit = total['cr'] / total['p'] * 100 if total['p'] else 0
    pct_miss = total['cm'] / total['p'] * 100 if total['p'] else 0
    print(f"    Cache Hit:           {total['cr']:,} ({pct_hit:.1f}%)")
    print(f"    Cache Miss:          {total['cm']:,} ({pct_miss:.1f}%)")
    print(f"    Avg Input/Request:   {total['p'] / n:,.0f}")
    print(f"    Avg Output/Request:  {total['c'] / n:,.0f}")
    print(f"    Avg Cache Hit/Req:   {total['cr'] / n:,.0f}")
    print(f"    Avg Cache Miss/Req:  {total['cm'] / n:,.0f}")
    print(f"    Avg Input/Day:       {total['p'] / day_secs:,.0f}")
    print(f"    Avg Output/Day:      {total['c'] / day_secs:,.0f}")
    print(f"    Avg Cache Hit/Day:   {total['cr'] / day_secs:,.0f}")
    print(f"    Avg Cache Miss/Day:  {total['cm'] / day_secs:,.0f}")
    print(f"    Total Time:          {total['t']:.2f}s")
    print(f"    Avg Time/Request:    {total['t'] / n:.2f}s")
    print(f"    Total Output tok/s:  {total['c'] / total['t']:.1f}")
    if total["cost"] > 0:
        print(f"    Total Cost:          ${total['cost']:.6f}\n")
    else:
        print()


if __name__ == "__main__":
    main()
