"""Minimal logging utility for consistent output formatting

Colors are imported from Config.colors to maintain single source of truth.
"""

import os
from typing import Optional
from dataclasses import dataclass


# Import colors from Config (single source of truth)
# This is deferred to avoid circular imports
def _get_colors():
    """Get colors from Config (deferred import to avoid circular dependency)"""
    from aicoder.core.config import Config
    return Config.colors


def _is_debug() -> bool:
    """Check if debug mode is enabled"""
    return os.environ.get("DEBUG") == "1"


@dataclass
class LogOptions:
    """Options for log formatting"""

    color: Optional[str] = None
    debug: bool = False
    bold: bool = False


class LogUtils:
    """
    Minimal logging utility for consistent output formatting
    All colors come from Config.colors for consistency.
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

        colors = _get_colors()

        if color:
            format_code = f"{colors['bold']}{color}" if bold else color
            print(f"{format_code}{message}{colors['reset']}")
        elif bold:
            print(f"{colors['bold']}{message}{colors['reset']}")
        else:
            print(message)

    @staticmethod
    def error(message: str) -> None:
        """Print error message (always shows, red by default)"""
        colors = _get_colors()
        LogUtils.print(message, LogOptions(color=colors["red"]))

    @staticmethod
    def success(message: str) -> None:
        """Print success message (always shows, green by default)"""
        colors = _get_colors()
        LogUtils.print(message, LogOptions(color=colors["green"]))

    @staticmethod
    def warn(message: str) -> None:
        """Print warning message (always shows, yellow by default)"""
        colors = _get_colors()
        LogUtils.print(message, LogOptions(color=colors["yellow"]))

    @staticmethod
    def debug(message: str, color: Optional[str] = None) -> None:
        """Print debug message (only shows when debug enabled)"""
        colors = _get_colors()
        LogUtils.print(message, LogOptions(color=color or colors["yellow"], debug=True))


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
    colors = _get_colors()
    LogUtils.print(message, LogOptions(color=colors["blue"]))
