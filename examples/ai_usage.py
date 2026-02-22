#!/usr/bin/env python3
"""AI Usage Statistics Reporter.

Finds all .aicoder/stats.log files and aggregates usage statistics.

Usage:
    python ai_usage.py [24h|week|month|year|hours <N>|days <N>|<start_date> <end_date>]
    Default: last 24 hours. Date format: YYYY-MM-DD
"""

from collections import defaultdict
from datetime import datetime, timedelta, UTC
from pathlib import Path


def get_time_range(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) datetime for a period in UTC (naive for file comparison)."""
    now = datetime.now(UTC).replace(tzinfo=None)
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
            now = datetime.now(UTC).replace(tzinfo=None)
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
    files = list(Path(".").rglob(".aicoder/stats.log"))
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
