"""
Stream utilities for reading input/output
Ported exactly from TypeScript version
"""

import sys


def read_stdin_as_string() -> str:
    """Read all content from stdin and return as trimmed string"""
    if not sys.stdin.isatty():
        content = sys.stdin.read()
        return content.strip()
    return ""
