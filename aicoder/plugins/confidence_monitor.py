"""Confidence monitoring plugin.

When MONITOR_CONFIDENCE_LEVEL=1:
- Injects optional `confidence` param (0-10) into run_shell_command schema
- Adds system prompt instruction telling the AI to self-score
- Prints [confidence_monitor] <level> with color: 0-3 red, 4-6 yellow, 7-10 green

Vet/tmux capture-pane scrapes for auditing.
"""

import copy
import os

from typing import Optional

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


_SYSTEM_INSTRUCTION = """
## Confidence self-assessment
For every `run_shell_command`, include a `confidence` parameter (0-10):
0=completely guessing, 5=moderately sure, 10=absolutely certain.
Be honest. This is used for quality monitoring.
"""


def _value_color(confidence: int) -> str:
    """Map confidence 0-10 to terminal color."""
    if confidence >= 7:
        return Config.colors["green"]
    if confidence >= 4:
        return Config.colors["yellow"]
    return Config.colors["red"]


_ROLLING_WINDOW = 5


def create_plugin(ctx):
    if os.environ.get("MONITOR_CONFIDENCE_LEVEL") != "1":
        return

    colors = Config.colors
    confidences: list = []  # rolling window

    def on_system_prompt_append():
        return _SYSTEM_INSTRUCTION

    def modify_tool_definitions(tools):
        """Inject optional confidence param into run_shell_command schema."""
        if "run_shell_command" not in tools:
            return tools

        tools = copy.deepcopy(tools)
        params = tools["run_shell_command"].get("parameters", {})
        properties = params.get("properties", {})

        properties["confidence"] = {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
            "description": "Self-assessed confidence (0-10). "
                           "0=unsure, 10=certain.",
        }
        return tools

    def _print_confidence(confidence, prefix=""):
        tag = f"{colors['bold']}{colors['yellow']}[confidence_monitor]{colors['reset']}"
        val = f"{_value_color(confidence)}{confidence}{colors['reset']}"
        LogUtils.print(f"{tag} {prefix}{val}")

    def before_approval(tool_name, arguments):
        if tool_name != "run_shell_command":
            return None
        if os.environ.get("MONITOR_CONFIDENCE_BEFORE_APPROVAL") != "1":
            return None
        confidence = arguments.get("confidence")
        if confidence is not None:
            _print_confidence(confidence, prefix="before-approval: ")
        return None  # Don't affect approval decision

    def after_tool(tool_name, arguments, result):
        if tool_name != "run_shell_command":
            return
        confidence = arguments.get("confidence")
        if confidence is not None:
            _print_confidence(confidence)
            confidences.append(confidence)
            if len(confidences) > _ROLLING_WINDOW:
                confidences.pop(0)

    def on_context_bar() -> Optional[str]:
        if not confidences:
            return None
        avg = sum(confidences) / len(confidences)
        c = _value_color(int(avg))
        return f"conf:{c}{avg:.1f}{colors['reset']}"

    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)
    ctx.register_hook("modify_tool_definitions", modify_tool_definitions)
    ctx.register_hook("before_approval_prompt", before_approval)
    ctx.register_hook("after_single_tool_execution", after_tool)
    ctx.register_hook("on_context_bar", on_context_bar)
