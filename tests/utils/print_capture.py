#!/usr/bin/env python3

"""
Print capture utility for testing AI Coder output with ANSI color codes.

This class monkey patches sys.stdout to capture all print output including
ANSI escape sequences for colors, allowing verification of exact formatting.
"""

import sys
import io
from typing import List, Optional, TextIO
from contextlib import contextmanager


class PrintCapture:
    """
    Captures all print output including ANSI color codes.
    
    Usage:
        with PrintCapture() as capture:
            print("test output")
            captured = capture.get_output()
    """
    
    def __init__(self):
        self._original_stdout: Optional[TextIO] = None
        self._captured_output: List[str] = []
        self._buffer: Optional[io.StringIO] = None
        self._active = False
    
    def start_capture(self) -> None:
        """Start capturing print output."""
        if self._active:
            return
        
        self._original_stdout = sys.stdout
        self._buffer = io.StringIO()
        self._captured_output = []
        
        # Replace stdout with our buffer
        sys.stdout = self._buffer  # type: ignore
        self._active = True
    
    def stop_capture(self) -> None:
        """Stop capturing and restore original stdout."""
        if not self._active:
            return
        
        # Restore original stdout
        sys.stdout = self._original_stdout
        self._active = False
        
        # Get all captured content
        if self._buffer:
            content = self._buffer.getvalue()
            self._captured_output = content.splitlines(keepends=True)
    
    def get_output(self) -> List[str]:
        """Get captured output as list of lines."""
        if self._active:
            # If still capturing, get current content
            if self._buffer:
                content = self._buffer.getvalue()
                return content.splitlines(keepends=True)
            return []
        return self._captured_output.copy()
    
    def get_output_string(self) -> str:
        """Get captured output as single string."""
        return ''.join(self.get_output())
    
    def get_plain_output(self) -> str:
        """Get captured output with ANSI codes stripped."""
        output = self.get_output_string()
        # Remove ANSI escape sequences
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', output)
    
    def clear(self) -> None:
        """Clear captured output."""
        if self._active and self._buffer:
            self._buffer.seek(0)
            self._buffer.truncate(0)
        self._captured_output = []
    
    def reset(self) -> None:
        """Reset capture state completely."""
        self.stop_capture()
        self.clear()
        self._buffer = None
        self._original_stdout = None
    
    @contextmanager
    def __enter__(self):
        """Context manager entry."""
        self.start_capture()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_capture()
    
    def contains_line(self, text: str) -> bool:
        """Check if captured output contains a line with specific text."""
        for line in self.get_output():
            if text in line:
                return True
        return False
    
    def contains_exact_line(self, line: str) -> bool:
        """Check if captured output contains an exact line match."""
        return line in self.get_output()
    
    def count_lines_with_text(self, text: str) -> int:
        """Count lines containing specific text."""
        return sum(1 for line in self.get_output() if text in line)
    
    def get_lines_with_text(self, text: str) -> List[str]:
        """Get all lines containing specific text."""
        return [line for line in self.get_output() if text in line]
    
    def has_ansi_codes(self) -> bool:
        """Check if captured output contains ANSI escape codes."""
        output = self.get_output_string()
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return bool(ansi_escape.search(output))
    
    def get_colored_lines(self, color_code: str) -> List[str]:
        """Get lines containing specific ANSI color code."""
        return [line for line in self.get_output() if color_code in line]


# ANSI color codes for testing
class ANSICodes:
    """Standard ANSI color codes for testing."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\x1b[33m'  # Standard yellow (matches system output)
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'  # Standard yellow background
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'