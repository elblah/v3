"""
Centralized tool output formatter
Following TypeScript structure exactly
"""

import json
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass

from aicoder.core.config import Config


@dataclass
class ToolOutput:
    tool: str
    friendly: Optional[str] = None  # Human-friendly message when detail mode is OFF
    important: Optional[Dict[str, Any]] = None  # Structured data when detail mode is ON
    detailed: Optional[Dict[str, Any]] = None
    results: Optional[Dict[str, Any]] = None
    approval_shown: Optional[bool] = (
        None  # Flag to indicate approval details were already displayed
    )


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    success: bool = True
    friendly: Optional[str] = None


@dataclass
class ToolPreview:
    tool: str
    summary: str  # Brief description of the change
    content: str  # The preview content (whatever the tool generates)
    warning: Optional[str] = None  # Any warnings about the operation
    can_approve: bool = False  # Whether this operation can be auto-approved
    is_diff: bool = False  # Whether the content is a diff that needs coloring


class ToolFormatter:
    """Tool formatter following TypeScript patterns exactly"""

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
    def format_for_ai(output: ToolOutput) -> str:
        """Format tool output for AI consumption
        Always returns the full formatted output regardless of detail mode"""
        lines = []
        indent = "  "  # 2 spaces for cleaner alignment

        # Always show important info (full output for AI)
        if output.important:
            for key, value in output.important.items():
                label = ToolFormatter._format_label(key)
                lines.append(
                    f"{indent}{label}{ToolFormatter._format_value_for_ai(value)}"
                )

        # Always show detailed info (full output for AI)
        if output.detailed:
            for key, value in output.detailed.items():
                label = ToolFormatter._format_label(key)
                lines.append(
                    f"{indent}{label}{ToolFormatter._format_value_for_ai(value)}"
                )

        # Always show results (except for showWhenDetailOff flag)
        if output.results:
            for key, value in output.results.items():
                if key != "showWhenDetailOff":
                    label = ToolFormatter._format_label(key)
                    lines.append(
                        f"{indent}{label}{ToolFormatter._format_value_for_ai(value)}"
                    )

        return "\n".join(lines)

    @staticmethod
    def format_for_display(output: ToolOutput) -> Optional[str]:
        """Format tool output for local display (always show friendly when available)"""
        return output.friendly

    @staticmethod
    def format_preview(preview) -> str:
        """Format preview for approval matching TypeScript exactly"""
        from aicoder.utils.log import LogUtils, LogOptions

        lines = []

        lines.append(
            f"{Config.colors['cyan']}[PREVIEW] {preview.summary}{Config.colors['reset']}"
        )

        if preview.warning:
            lines.append(
                f"{Config.colors['yellow']}[!] Warning: {preview.warning}{Config.colors['reset']}"
            )

        lines.append("")

        # Colorize diff content if explicitly marked as diff
        if preview.is_diff:
            lines.append(ToolFormatter.colorize_diff(preview.content))
        else:
            lines.append(preview.content)

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
