"""Minimal logging utility for consistent output formatting"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class LogOptions:
    """Options for log formatting"""

    color: Optional[str] = None
    debug: bool = False
    bold: bool = False


# ANSI color codes
class Colors:
    reset = "\x1b[0m"
    bold = "\x1b[1m"
    dim = "\x1b[2m"
    black = "\x1b[30m"
    red = "\x1b[31m"
    green = "\x1b[32m"
    yellow = "\x1b[33m"
    blue = "\x1b[34m"
    magenta = "\x1b[35m"
    cyan = "\x1b[36m"
    white = "\x1b[37m"
    bright_green = "\x1b[92m"
    bright_red = "\x1b[91m"
    bright_yellow = "\x1b[93m"
    bright_blue = "\x1b[94m"
    bright_magenta = "\x1b[95m"
    bright_cyan = "\x1b[96m"
    bright_white = "\x1b[97m"


def _is_debug() -> bool:
    """Check if debug mode is enabled"""
    return os.environ.get("DEBUG") == "1"


class LogUtils:
    """
    Minimal logging utility for consistent output formatting
    
    """

    @staticmethod
    def print(message: str, options: Optional[LogOptions] = None, **kwargs) -> None:
        """
        Print message with optional formatting
        @param message: Message to print
        @param options: Optional formatting options
        """
        if options is None:
            # Allow direct keyword arguments for convenience
            if kwargs:
                options = LogOptions(
                    color=kwargs.get("color"),
                    debug=kwargs.get("debug", False),
                    bold=kwargs.get("bold", False),
                )
            else:
                options = LogOptions()

        color = options.color
        debug = options.debug
        bold = options.bold

        if debug and not _is_debug():
            return

        if color:
            format_code = f"{Colors.bold}{color}" if bold else color
            print(f"{format_code}{message}{Colors.reset}")
        elif bold:
            print(f"{Colors.bold}{message}{Colors.reset}")
        else:
            print(message)

    @staticmethod
    def error(message: str) -> None:
        """Print error message (always shows, red by default)"""
        LogUtils.print(message, LogOptions(color=Colors.red))

    @staticmethod
    def success(message: str) -> None:
        """Print success message (always shows, green by default)"""
        LogUtils.print(message, LogOptions(color=Colors.green))

    @staticmethod
    def warn(message: str) -> None:
        """Print warning message (always shows, yellow by default)"""
        LogUtils.print(message, LogOptions(color=Colors.yellow))

    @staticmethod
    def debug(message: str, color: Optional[str] = None) -> None:
        """Print debug message (only shows when debug enabled)"""
        LogUtils.print(message, LogOptions(color=color or Colors.yellow, debug=True))


# Standalone convenience functions
def success(message: str) -> None:
    """Print success message"""
    LogUtils.success(message)


def warn(message: str) -> None:
    """Print warning message"""
    LogUtils.warn(message)


def error(message: str) -> None:
    """Print error message"""
    LogUtils.error(message)


def debug(message: str, color: Optional[str] = None) -> None:
    """Print debug message"""
    LogUtils.debug(message, color)


def info(message: str) -> None:
    """Print info message"""
    LogUtils.print(message, LogOptions(color=Colors.blue))
