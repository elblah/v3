#!/usr/bin/env python3
"""
AI Usage Statistics Reporter

Finds all .aicoder/stats.log files in the directory tree and aggregates usage statistics.

Usage:
    python ai_usage.py [24h|week|month|year|<start_date> <end_date>]
    
    Default: last 24 hours
    Date format: YYYY-MM-DD
"""

import os
import sys
import warnings
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

# Suppress utcnow deprecation warning for Python 3.12+
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*utcnow.*")


def find_stats_logs(start_dir="."):
    """Find all stats.log files inside .aicoder directories."""
    stats_files = []
    for root, dirs, files in os.walk(start_dir):
        if ".aicoder" in root and "stats.log" in files:
            stats_files.append(os.path.join(root, "stats.log"))
    return stats_files


def parse_datetime(dt_str):
    """Parse YYYY-MM-DD format."""
    return datetime.strptime(dt_str, "%Y-%m-%d")


def get_time_range(period):
    """Get start/end datetime for a time period (in UTC)."""
    now = datetime.utcnow()
    
    if period == "24h":
        return now - timedelta(days=1), now
    elif period == "week":
        return now - timedelta(weeks=1), now
    elif period == "month":
        return now - timedelta(days=30), now
    elif period == "year":
        return now - timedelta(days=365), now
    else:
        return None, None


def parse_stats_file(filepath, start_dt, end_dt):
    """Parse a stats.log file and return filtered entries."""
    entries = []
    
    # Format: timestamp|base_url|model|prompt_tokens|completion_tokens|elapsed_seconds
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split("|")
            if len(parts) != 6:
                continue
            
            try:
                timestamp_str, base_url, model, prompt_tokens, completion_tokens, elapsed = parts
                
                # Parse timestamp
                timestamp = datetime.fromisoformat(timestamp_str)
                
                # Filter by time range
                if start_dt and end_dt:
                    if timestamp < start_dt or timestamp > end_dt:
                        continue
                
                entries.append({
                    "timestamp": timestamp,
                    "base_url": base_url,
                    "model": model,
                    "prompt_tokens": int(prompt_tokens),
                    "completion_tokens": int(completion_tokens),
                    "elapsed": float(elapsed),
                })
            except (ValueError, IndexError):
                continue
    
    return entries


def format_number(n):
    """Format number with commas."""
    return f"{n:,}"


def main():
    # Parse time period argument
    period = sys.argv[1] if len(sys.argv) > 1 else "24h"
    
    # Handle custom date range
    if len(sys.argv) >= 3:
        try:
            start_dt = parse_datetime(sys.argv[1])
            end_dt = parse_datetime(sys.argv[2])
            # End of day for end_dt
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            period_label = f"{sys.argv[1]} to {sys.argv[2]}"
        except ValueError:
            print(f"Error: Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        start_dt, end_dt = get_time_range(period)
        period_label = period
    
    if not start_dt or not end_dt:
        print(f"Error: Unknown period '{period}'")
        print("Usage: ai_usage.py [24h|week|month|year|<start_date> <end_date>]")
        sys.exit(1)
    
    # Find all stats.log files
    stats_files = find_stats_logs(".")
    
    if not stats_files:
        print("No .aicoder/stats.log files found in current directory tree.")
        sys.exit(0)
    
    # Parse all files
    all_entries = []
    for filepath in stats_files:
        entries = parse_stats_file(filepath, start_dt, end_dt)
        all_entries.extend(entries)
    
    if not all_entries:
        print(f"No API requests found for period: {period_label}")
        sys.exit(0)
    
    # Aggregate by base_url -> model
    aggregated = defaultdict(lambda: defaultdict(lambda: {
        "requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_time": 0.0,
    }))
    
    for entry in all_entries:
        data = aggregated[entry["base_url"]][entry["model"]]
        data["requests"] += 1
        data["prompt_tokens"] += entry["prompt_tokens"]
        data["completion_tokens"] += entry["completion_tokens"]
        data["total_time"] += entry["elapsed"]
    
    # Print results
    print(f"\n=== AI Usage Report ({period_label}) ===\n")
    
    total_requests = 0
    total_prompt = 0
    total_completion = 0
    total_time = 0.0
    
    for base_url in sorted(aggregated.keys()):
        models = aggregated[base_url]
        print(f"{base_url}")
        
        for model in sorted(models.keys()):
            data = models[model]
            avg_time = data["total_time"] / data["requests"] if data["requests"] > 0 else 0
            
            print(f"    Model: {model}")
            print(f"        Requests:       {format_number(data['requests'])}")
            print(f"        Input Tokens:   {format_number(data['prompt_tokens'])}")
            print(f"        Output Tokens:  {format_number(data['completion_tokens'])}")
            print(f"        Avg Req Time:   {avg_time:.2f}s")
            print()
            
            total_requests += data["requests"]
            total_prompt += data["prompt_tokens"]
            total_completion += data["completion_tokens"]
            total_time += data["total_time"]
    
    # Total summary
    print("-" * 50)
    print("TOTAL SUMMARY")
    print(f"    Total Requests:      {format_number(total_requests)}")
    print(f"    Total Input Tokens:  {format_number(total_prompt)}")
    print(f"    Total Output Tokens: {format_number(total_completion)}")
    print(f"    Total Time:          {total_time:.2f}s")
    if total_requests > 0:
        print(f"    Avg Time/Request:    {total_time / total_requests:.2f}s")
    print()


if __name__ == "__main__":
    main()
