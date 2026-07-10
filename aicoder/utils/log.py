"""Minimal logging utility for consistent output formatting

Colors are imported from Config.colors to maintain single source of truth.

Usage:
    # Colored print with color name (preferred)
    LogUtils.printc("message", color="red")
    LogUtils.printc("error", color="green")

    # Convenience methods (recommended for readability)
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
    from aicoder.utils.log import success, warn, error, info, debug, printc
"""

import os
import sys
import builtins
from datetime import datetime
from typing import Optional

# Simple options class instead of dataclass (avoids 150ms import cost)
class LogOptions:
    """Options for log formatting"""
    __slots__ = ('color', 'debug', 'bold')
    def __init__(self, color: Optional[str] = None, debug: bool = False, bold: bool = False):
        self.color = color
        self.debug = debug
        self.bold = bold


# Import colors from Config (single source of truth)
# This is deferred to avoid circular imports
def _get_colors():
    """Get colors from Config (deferred import to avoid circular dependency)"""
    from aicoder.core.config import Config
    return Config.colors


def _is_debug() -> bool:
    """Check if debug mode is enabled"""
    from aicoder.core.config import Config
    return Config.debug()


def _get_error_log_path() -> str:
    """Get path to error log file"""
    base = os.getcwd()
    return os.path.join(base, ".aicoder", "errors.log")


def _append_error_log(message: str, traceback_str: str) -> None:
    """Append error to log file"""
    log_path = _get_error_log_path()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timestamp = datetime.now().isoformat()
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
        f.write(traceback_str)
        f.write("\n")


class LogUtils:
    """
    Minimal logging utility for consistent output formatting
    All colors come from Config.colors for consistency.
    """

    @staticmethod
    def printc(message: str, options: Optional[LogOptions] = None,
               color: Optional[str] = None, bold: bool = False,
               debug: bool = False, stderr: bool = False) -> None:
        """
        Print message with optional coloring.

        Args:
            message: Message to print
            options: LogOptions instance (for backward compatibility)
            color: Color name from Config.colors (e.g., "red", "green", "yellow", "cyan")
            bold: Apply bold formatting
            debug: Only print when DEBUG=1
            stderr: Print to stderr instead of stdout

        Usage:
            LogUtils.printc("text")
            LogUtils.printc("text", color="red")
            LogUtils.printc("text", color="red", bold=True)
            LogUtils.printc("text", LogOptions(color="red"))  # backward compatible
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
        file = sys.stderr if stderr else None

        if effective_color:
            # Check if it's an ANSI code (starts with escape character) or a color name
            if effective_color.startswith('\x1b'):
                # It's already an ANSI escape code, use it directly
                ansi_color = effective_color
            else:
                # It's a color name, look it up
                ansi_color = colors.get(effective_color, "")

            if ansi_color:
                format_code = f"{colors['bold']}{ansi_color}" if effective_bold else ansi_color
                builtins.print(f"{format_code}{message}{colors['reset']}", file=file)
            else:
                builtins.print(message, file=file)
        elif effective_bold:
            builtins.print(f"{colors['bold']}{message}{colors['reset']}", file=file)
        else:
            builtins.print(message, file=file)

    @staticmethod
    def print(message: str = "", options: Optional[LogOptions] = None,
              color: Optional[str] = None, bold: bool = False,
              debug: bool = False) -> None:
        """
        Print message with optional formatting (alias for printc for backward compatibility).

        Args:
            message: Message to print (default: empty string for blank line)
            options: LogOptions instance (for backward compatibility)
            color: Color name from Config.colors (e.g., "red", "green", "yellow")
            bold: Apply bold formatting
            debug: Only print when DEBUG=1
        """
        LogUtils.printc(message, options=options, color=color, bold=bold, debug=debug)

    # === Core Status Methods ===

    @staticmethod
    def error(message: str) -> None:
        """Print error message (red) to stderr. Auto-detects exception context and prints/logs stack."""
        LogUtils.printc(message, color="red", stderr=True)
        exc_info = sys.exc_info()[0]
        if exc_info is not None and exc_info is not KeyboardInterrupt:
            import traceback
            tb = traceback.format_exc()
            LogUtils.printc(tb, color="red", stderr=True)
            _append_error_log(message, tb)

    @staticmethod
    def success(message: str) -> None:
        """Print success message (green)"""
        LogUtils.printc(message, color="green")

    @staticmethod
    def warn(message: str) -> None:
        """Print warning message (yellow) to stderr"""
        LogUtils.printc(message, color="yellow", stderr=True)

    @staticmethod
    def info(message: str) -> None:
        """Print info message (blue)"""
        LogUtils.printc(message, color="blue")

    @staticmethod
    def debug(message: str, color: Optional[str] = None) -> None:
        """Print debug message (only when DEBUG=1, yellow by default)"""
        LogUtils.printc(message, color=color or "yellow", debug=True)

    # === Additional Formatting Methods ===

    @staticmethod
    def tip(message: str) -> None:
        """Print tip message (cyan)"""
        LogUtils.printc(message, color="cyan")

    @staticmethod
    def hint(message: str) -> None:
        """Print hint message (magenta)"""
        LogUtils.printc(message, color="magenta")

    @staticmethod
    def note(message: str) -> None:
        """Print note message (bright blue)"""
        LogUtils.printc(message, color="brightBlue")

    @staticmethod
    def dim(message: str) -> None:
        """Print dim/subtle message (grey)"""
        LogUtils.printc(message, color="dim")

    @staticmethod
    def strong(message: str) -> None:
        """Print bold/emphasized message"""
        LogUtils.printc(message, bold=True)


# === Standalone Convenience Functions ===

def success(message: str) -> None:
    """Print success message (green)"""
    LogUtils.success(message)


def warn(message: str) -> None:
    """Print warning message (yellow)"""
    LogUtils.warn(message)


def error(message: str) -> None:
    """Print error message (red). Auto-detects exception context and prints/logs stack."""
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


def printc(message: str = "", options: Optional[LogOptions] = None,
           color: Optional[str] = None, bold: bool = False,
           debug: bool = False) -> None:
    """Print message with optional coloring (standalone function)"""
    LogUtils.printc(message, options=options, color=color, bold=bold, debug=debug)


def print(message: str = "", options: Optional[LogOptions] = None,
          color: Optional[str] = None, bold: bool = False,
          debug: bool = False) -> None:
    """Print message with optional formatting (backward compatible alias for printc)"""
    LogUtils.printc(message, options=options, color=color, bold=bold, debug=debug)


def cyan(message: str) -> None:
    """Print cyan-colored message"""
    LogUtils.printc(message, color="cyan")
