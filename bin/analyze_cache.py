#!/usr/bin/env python3
"""Analyze cache drops from stats.log.

Usage:
  python3 analyze_cache.py [--json] [path/to/stats.log]

Detects cache drops by comparing cached_tokens between consecutive entries.
Old pipe-delimited format (no cache info) is skipped automatically.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path


def parse_stats(path):
    """Yield parsed JSON entries from stats.log, skipping old pipe format."""
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def analyze(entries):
    """Analyze cache behavior per (api_provider, model, url) group."""
    groups = defaultdict(list)
    for e in entries:
        key = (e.get("api_provider", "?"), e.get("model", "?"), e.get("url", "?"))
        groups[key].append(e)

    results = {}
    for key, group in groups.items():
        provider, model, url = key
        total = len(group)
        drops = 0
        drop_details = []
        prev_cached = None
        prev_session = None

        for i, e in enumerate(group):
            usage = e.get("usage") or {}
            ptd = usage.get("prompt_tokens_details") or {}
            cached = ptd.get("cached_tokens")

            if cached is None:
                continue  # no cache info for this entry

            # Reset baseline on first entry OR session change.
            # Each session has its own KV cache on the provider side;
            # comparing cached_tokens across sessions produces false drops
            # because every new session starts with ~0 cached tokens.
            current_session = e.get("session")
            if prev_cached is None or current_session != prev_session:
                prev_cached = cached
                prev_session = current_session
                continue

            # Detect meaningful cache drop (>10% loss)
            if cached < prev_cached * 0.9:
                pct = (1 - cached / prev_cached) * 100
                drops += 1
                drop_details.append({
                    "ts": e.get("ts"),
                    "prev": prev_cached,
                    "curr": cached,
                    "pct": round(pct, 1),
                })

            prev_cached = cached
            prev_session = current_session

        # Count entries that actually have cache tracking
        tracked = sum(1 for e in group
                      if (e.get("usage") or {}).get("prompt_tokens_details") is not None
                      and (e["usage"]["prompt_tokens_details"] or {}).get("cached_tokens") is not None)

        results[key] = {
            "provider": provider,
            "model": model,
            "url": url.replace("https://", "").rstrip("/"),
            "total_calls": total,
            "tracked_calls": tracked,
            "cache_drops": drops,
            "drop_pct": round(drops / tracked * 100, 1) if tracked else 0,
            "drops": drop_details[-5:] if drop_details else [],  # last 5 drops
        }

    return results


def print_table(results):
    """Print a human-readable table."""
    rows = []
    for key, r in results.items():
        rows.append((
            r["provider"],
            r["model"],
            r["url"],
            r["total_calls"],
            r["tracked_calls"],
            r["cache_drops"],
            f'{r["drop_pct"]}%',
        ))

    if not rows:
        print("No cache-tracking entries found in stats.log.")
        return

    # Header
    print(f"{'Provider':<12} {'Model':<22} {'URL':<30} {'Total':>6} {'Tracked':>8} {'Drops':>6} {'Drop%':>6}")
    print("-" * 90)
    rows.sort(key=lambda r: -r[4])  # sort by tracked count desc
    for r in rows:
        print(f"{r[0]:<12} {r[1]:<22} {r[2]:<30} {r[3]:>6} {r[4]:>8} {r[5]:>6} {r[6]:>6}")

    print()
    # Show recent drops for groups with drops
    for key, r in results.items():
        if not r["drops"]:
            continue
        print(f"\n--- Recent drops ({r['provider']}/{r['model']} @ {r['url']}) ---")
        for d in r["drops"]:
            print(f"  {d['ts']}: {d['prev']} -> {d['curr']} ({d['pct']}% drop)")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else ".aicoder/stats.log"
    json_out = "--json" in sys.argv

    entries = list(parse_stats(path))
    if not entries:
        print(f"No JSON entries found in {path}")
        sys.exit(1)

    results = analyze(entries)

    if json_out:
        print(json.dumps(results, indent=2, default=str))
    else:
        print_table(results)


if __name__ == "__main__":
    main()
