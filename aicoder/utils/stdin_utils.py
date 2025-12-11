"""
Utilities for reading from stdin
Synchronous version
"""

import sys


def read_stdin_as_string() -> str:
    """Read all content from stdin if piped"""
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""
