"""Minimal logging utility for consistent output formatting

Colors are imported from Config.colors to maintain single source of truth.

Usage:
    # Simple usage with keyword arguments
    LogUtils.print("message", color="red", bold=True)
    LogUtils.print("error", color="green")

    # Convenience methods
    LogUtils.success("Done!")
    LogUtils.warn("Check this")
    LogUtils.error("Failed!")
    LogUtils.info(" FYI")
    LogUtils.debug("details")  # Only shows when DEBUG=1

    # Additional formatting methods
    LogUtils.tip("Pro tip")
    LogUtils.hint("Quick hint")
    LogUtils.note("Important note")
    LogUtils.dim("Subtle text")
    LogUtils.strong("Emphasized text")

    # Standalone functions also available
    from aicoder.utils.log import success, warn, error, info, debug
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
    def print(message: str, options: Optional[LogOptions] = None,
              color: Optional[str] = None, bold: bool = False,
              debug: bool = False) -> None:
        """
        Print message with optional formatting.

        Args:
            message: Message to print
            options: LogOptions instance (for backward compatibility)
            color: Color name from Config.colors (e.g., "red", "green", "yellow")
            bold: Apply bold formatting
            debug: Only print when DEBUG=1

        Usage:
            LogUtils.print("text")
            LogUtils.print("text", color="red")
            LogUtils.print("text", color="red", bold=True)
            LogUtils.print("text", LogOptions(color="red"))  # backward compatible
        """
        # Handle kwargs-style arguments (priority over LogOptions)
        effective_color = color
        effective_debug = debug
        effective_bold = bold

        if options is not None:
            # Backward compatibility: LogOptions takes precedence if no kwargs provided
            # This allows: LogUtils.print("msg", LogOptions(color="red"))
            if color is None and not bold and not debug:
                effective_color = options.color
                effective_debug = options.debug
                effective_bold = options.bold

        if effective_debug and not _is_debug():
            return

        colors = _get_colors()

        if effective_color:
            format_code = f"{colors['bold']}{effective_color}" if effective_bold else effective_color
            print(f"{format_code}{message}{colors['reset']}")
        elif effective_bold:
            print(f"{colors['bold']}{message}{colors['reset']}")
        else:
            print(message)

    # === Core Status Methods ===

    @staticmethod
    def error(message: str) -> None:
        """Print error message (red)"""
        colors = _get_colors()
        LogUtils.print(message, color=colors["red"])

    @staticmethod
    def success(message: str) -> None:
        """Print success message (green)"""
        colors = _get_colors()
        LogUtils.print(message, color=colors["green"])

    @staticmethod
    def warn(message: str) -> None:
        """Print warning message (yellow)"""
        colors = _get_colors()
        LogUtils.print(message, color=colors["yellow"])

    @staticmethod
    def info(message: str) -> None:
        """Print info message (blue)"""
        colors = _get_colors()
        LogUtils.print(message, color=colors["blue"])

    @staticmethod
    def debug(message: str, color: Optional[str] = None) -> None:
        """Print debug message (only when DEBUG=1, yellow by default)"""
        colors = _get_colors()
        LogUtils.print(message, color=color or colors["yellow"], debug=True)

    # === Additional Formatting Methods ===

    @staticmethod
    def tip(message: str) -> None:
        """Print tip message (cyan)"""
        colors = _get_colors()
        LogUtils.print(message, color=colors["cyan"])

    @staticmethod
    def hint(message: str) -> None:
        """Print hint message (magenta)"""
        colors = _get_colors()
        LogUtils.print(message, color=colors["magenta"])

    @staticmethod
    def note(message: str) -> None:
        """Print note message (bright blue)"""
        colors = _get_colors()
        LogUtils.print(message, color=colors["brightBlue"])

    @staticmethod
    def dim(message: str) -> None:
        """Print dim/subtle message (grey)"""
        colors = _get_colors()
        LogUtils.print(message, color=colors["dim"])

    @staticmethod
    def strong(message: str) -> None:
        """Print bold/emphasized message"""
        LogUtils.print(message, bold=True)


# === Standalone Convenience Functions ===

def success(message: str) -> None:
    """Print success message (green)"""
    LogUtils.success(message)


def warn(message: str) -> None:
    """Print warning message (yellow)"""
    LogUtils.warn(message)


def error(message: str) -> None:
    """Print error message (red)"""
    LogUtils.error(message)


def info(message: str) -> None:
    """Print info message (blue)"""
    LogUtils.info(message)


def debug(message: str, color: Optional[str] = None) -> None:
    """Print debug message (only when DEBUG=1)"""
    LogUtils.debug(message, color)


def tip(message: str) -> None:
    """Print tip message (cyan)"""
    LogUtils.tip(message)


def hint(message: str) -> None:
    """Print hint message (magenta)"""
    LogUtils.hint(message)


def note(message: str) -> None:
    """Print note message (bright blue)"""
    LogUtils.note(message)


def dim(message: str) -> None:
    """Print dim/subtle message"""
    LogUtils.dim(message)


def strong(message: str) -> None:
    """Print bold/emphasized message"""
    LogUtils.strong(message)
