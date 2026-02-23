#!/usr/bin/env python3
"""AI Usage Statistics Reporter.

Finds all .aicoder/stats.log files and aggregates usage statistics.

Usage:
    python ai_usage.py [24h|week|month|year|hours <N>|days <N>|YYYY-MM-DD YYYY-MM-DD]
    python ai_usage.py update      # Force refresh cache
    python ai_usage.py clear-cache # Delete cache
    Default: last 24 hours (rolling, not calendar day)
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

CACHE_FILE = Path.home() / ".cache" / "ai_usage_dirs_cache.txt"
CACHE_MAX_AGE = timedelta(hours=3)


def get_cache_file() -> Path:
    """Ensure cache directory exists, return cache file path."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return CACHE_FILE


def read_cache() -> List[Path] | None:
    """Read cached stats.log paths if valid and fresh."""
    if not CACHE_FILE.exists():
        return None

    # Check cache age
    cache_mtime = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime, tz=timezone.utc).replace(tzinfo=None)
    if datetime.now(timezone.utc).replace(tzinfo=None) - cache_mtime > CACHE_MAX_AGE:
        return None

    try:
        paths = []
        for line in CACHE_FILE.read_text().splitlines():
            if line.strip():
                p = Path(line.strip())
                if p.exists():
                    paths.append(p)
        return paths if paths else None
    except (OSError, IOError):
        return None


def write_cache(paths: List[Path]) -> None:
    """Write stats.log paths to cache."""
    try:
        cache = get_cache_file()
        cache.write_text("\n".join(str(p) for p in paths))
    except (OSError, IOError):
        pass


def clear_cache() -> None:
    """Delete cache file if exists."""
    if CACHE_FILE.exists():
        try:
            CACHE_FILE.unlink()
        except (OSError, IOError):
            pass


def find_stats_files() -> List[Path]:
    """Find all stats.log files, using cache if available."""
    cwd = Path.cwd()
    home = Path.home()

    # Use cache only when running from home directory
    if cwd == home:
        cached = read_cache()
        if cached:
            return cached
        print("Cache miss, scanning for stats files... (this may take a while)", flush=True)

    # Search filesystem
    files = list(Path(".").rglob(".aicoder/stats.log"))
    # Convert to absolute paths for cache consistency
    files = [f.resolve() for f in files]

    # Write cache only when running from home directory
    if cwd == home and files:
        write_cache(files)
        print(f"Found {len(files)} stats files. Cached for 3 hours.", flush=True)

    return files


def get_time_range(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) datetime for a period in UTC."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = {
        "24h": timedelta(days=1),
        "week": timedelta(weeks=1),
        "month": timedelta(days=30),
        "year": timedelta(days=365),
    }.get(period)
    return (now - delta, now) if delta else (None, None)


def parse_stats(filepath: Path, start: datetime | None, end: datetime | None):
    """Parse a stats.log file, return entries within time range."""
    entries = []
    # Format: timestamp|base_url|model|prompt_tokens|completion_tokens|elapsed
    for line in filepath.read_text().splitlines():
        if not line or line.count("|") != 5:
            continue
        ts, url, model, p_tok, c_tok, elapsed = line.split("|")
        try:
            # Handle both T and underscore separators
            ts = ts.replace("_", "T")
            dt = datetime.fromisoformat(ts)
            if start and (dt < start or dt > end):
                continue
            entries.append({
                "url": url, "model": model,
                "prompt": int(p_tok), "completion": int(c_tok), "elapsed": float(elapsed),
            })
        except ValueError:
            continue
    return entries


def main():
    import sys
    args = sys.argv[1:]

    # Handle manual cache commands
    if "clear-cache" in args:
        clear_cache()
        print("Cache cleared.")
        sys.exit(0)
    elif "update" in args:
        args = [a for a in args if a != "update"]
        # Force refresh by clearing cache before search
        clear_cache()

    # Parse time range
    if len(args) >= 2 and args[0] in ("hours", "days", "minutes"):
        try:
            n = int(args[1])
            if args[0] == "hours":
                delta = timedelta(hours=n)
                label = f"last {n} hours"
            elif args[0] == "days":
                delta = timedelta(days=n)
                label = f"last {n} days"
            else:
                delta = timedelta(minutes=n)
                label = f"last {n} minutes"
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
            print("Usage: ai_usage.py [24h|week|month|year|minutes <N>|hours <N>|days <N>|<start_date> <end_date>]")
            sys.exit(1)
        label = period

    # Find and parse stats files
    files = find_stats_files()
    if not files:
        print("No .aicoder/stats.log files found.")
        sys.exit(0)

    entries = [e for f in files for e in parse_stats(f, start, end)]
    if not entries:
        print(f"No requests found for: {label}")
        sys.exit(0)

    # Aggregate: url -> model -> stats
    agg: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "p": 0, "c": 0, "t": 0.0}))
    for e in entries:
        agg[e["url"]][e["model"]]["n"] += 1
        agg[e["url"]][e["model"]]["p"] += e["prompt"]
        agg[e["url"]][e["model"]]["c"] += e["completion"]
        agg[e["url"]][e["model"]]["t"] += e["elapsed"]

    # Report
    print(f"\n=== AI Usage Report ({label}) ===\n")
    total = {"n": 0, "p": 0, "c": 0, "t": 0.0}

    for url in sorted(agg):
        print(url)
        for model in sorted(agg[url]):
            d = agg[url][model]
            avg = d["t"] / d["n"]
            print(f"    Model: {model}")
            print(f"        Requests:       {d['n']:,}")
            print(f"        Input Tokens:   {d['p']:,}")
            print(f"        Output Tokens:  {d['c']:,}")
            print(f"        Avg Req Time:   {avg:.2f}s\n")
            total["n"] += d["n"]
            total["p"] += d["p"]
            total["c"] += d["c"]
            total["t"] += d["t"]

    print("-" * 50)
    print("TOTAL SUMMARY")
    print(f"    Total Requests:      {total['n']:,}")
    print(f"    Total Input Tokens:  {total['p']:,}")
    print(f"    Total Output Tokens: {total['c']:,}")
    print(f"    Total Time:          {total['t']:.2f}s")
    print(f"    Avg Time/Request:    {total['t'] / total['n']:.2f}s\n")


if __name__ == "__main__":
    main()
