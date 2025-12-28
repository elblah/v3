"""
Centralized tool output formatter

"""

import json
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass

from aicoder.core.config import Config


class ToolFormatter:
    """Tool formatter"""

    @staticmethod
    def colorize_diff(diff_output: str) -> str:
        """Colorize diff output"""
        lines = diff_output.split("\n")
        colored_lines = []

        for line in lines:
            # Skip diff header lines (--- and +++)
            if line.startswith("---") or line.startswith("+++"):
                continue

            if line.startswith("-"):
                colored_lines.append(
                    f"{Config.colors['red']}{line}{Config.colors['reset']}"
                )
            elif line.startswith("+"):
                colored_lines.append(
                    f"{Config.colors['green']}{line}{Config.colors['reset']}"
                )
            elif line.startswith("@@"):
                colored_lines.append(
                    f"{Config.colors['cyan']}{line}{Config.colors['reset']}"
                )
            else:
                colored_lines.append(line)

        return "\n".join(colored_lines)

    @staticmethod
    def format_for_ai(result: Dict[str, Any]) -> str:
        """Format tool result for AI consumption - always returns detailed version"""
        return result["detailed"]

    @staticmethod
    def format_for_display(result: Dict[str, Any]) -> Optional[str]:
        """Format tool result for local display - always show friendly when available"""
        return result["friendly"]

    @staticmethod
    def format_preview(preview, file_path=None) -> str:
        """Format preview for approval - simplified design"""
        from aicoder.utils.log import LogUtils, LogOptions

        lines = []

        # Show file path if available
        if file_path:
            preview_title = file_path
        else:
            preview_title = "Preview"

        lines.append(
            f"{Config.colors['cyan']}[PREVIEW] {preview_title}{Config.colors['reset']}"
        )
        lines.append("")

        # Always show content - tools are responsible for formatting
        lines.append(preview.get("content", ""))

        return "\n".join(lines)

    @staticmethod
    def _format_label(key: str) -> str:
        """Format a label with consistent alignment"""
        # Capitalize first letter and replace underscores with spaces
        formatted = key[0].upper() + key[1:].replace("_", " ")
        return f"{formatted}:"

    @staticmethod
    def _format_value_for_ai(value: Any) -> str:
        """Format value for AI consumption (never truncates)"""
        if value is None:
            return " null"
        if isinstance(value, bool):
            return f" {value}"
        if isinstance(value, (int, float)):
            return f" {value}"
        if isinstance(value, str):
            return f" {value}"
        if isinstance(value, Exception):
            return f" {str(value)}"
        # For objects, JSON stringify with truncation
        json_str = json.dumps(value)
        return f" {json_str}"

    @staticmethod
    def _format_value(value: Any) -> str:
        """Format a value for display"""
        if value is None:
            return " null"
        if isinstance(value, bool):
            return f" {value}"
        if isinstance(value, (int, float)):
            return f" {value}"
        if isinstance(value, str):
            # Truncate very long strings in non-detail mode
            if not Config.detail_mode and len(value) > 100:
                return f" {value[:97]}..."
            return f" {value}"
        if isinstance(value, Exception):
            return f" {str(value)}"
        # For objects, JSON stringify with truncation
        json_str = json.dumps(value)
        if not Config.detail_mode and len(json_str) > 100:
            return f" {json_str[:97]}..."
        return f" {json_str}"
