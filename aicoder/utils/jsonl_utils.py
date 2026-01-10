"""JSONL utilities for session persistence"""

import json
from typing import List, Dict, Any


def read_file(path: str) -> List[Dict[str, Any]]:
    """Read JSONL file"""
    messages = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        # Skip invalid lines silently
                        continue
    except FileNotFoundError:
        pass  # Return empty list if file doesn't exist
    except Exception as e:
        raise Exception(f"Error reading JSONL file {path}: {e}")
    
    return messages


def write_file(path: str, messages: List[Dict[str, Any]]) -> None:
    """Write messages to JSONL file"""
    try:
        with open(path, "w") as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    except Exception as e:
        raise Exception(f"Error writing JSONL file {path}: {e}")