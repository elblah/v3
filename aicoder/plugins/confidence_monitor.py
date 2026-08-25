"""Confidence monitoring plugin.

When MONITOR_CONFIDENCE_LEVEL=1:
- Injects `confidence` param (0-10) into ALL tools
- Adds system prompt instruction telling the AI to self-score
- Prints [confidence_monitor] <level> with color: 0-3 red, 4-6 yellow, 7-10 green

Vet/tmux capture-pane scrapes for auditing.
"""

import copy

from typing import Optional

from aicoder.core.config import Config
from aicoder.utils.bool_utils import env_bool
from aicoder.utils.log import LogUtils

# Tools that modify state — approval/prompt gating still scoped to these
_MUTATION_TOOLS = {"run_shell_command", "write_file", "edit_file"}

_SYSTEM_INSTRUCTION = """
## Confidence self-assessment (session direction)
Include a `confidence` parameter (0-10) on all tools:
0=I'm lost / session direction unclear, 5=reasonably sure what you want,
10=certain I understand the goal and this action aligns.
Be honest. Low confidence means I need you to clarify or redirect.
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
    if not env_bool("MONITOR_CONFIDENCE_LEVEL"):
        return

    colors = Config.colors
    confidences: list = []  # rolling window

    def on_system_prompt_append():
        return _SYSTEM_INSTRUCTION

    def modify_tool_definitions(tools):
        """Inject confidence param into all tool schemas."""
        tools = copy.deepcopy(tools)
        conf_prop = {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
            "description": "Session direction confidence (0-10). "
                           "0=lost / goal unclear, 5=reasonably sure, "
                           "10=certain this aligns with what you want",
        }
        for name, tool_def in tools.items():
            params = tool_def.get("parameters", {})
            properties = params.get("properties", {})
            properties["confidence"] = conf_prop
            if "confidence" not in params.get("required", []):
                params.setdefault("required", []).append("confidence")
        return tools

    def _print_confidence(confidence, prefix=""):
        # Models may send confidence as string despite numeric schema
        confidence = float(confidence)
        tag = f"{colors['bold']}{colors['yellow']}[confidence_monitor]{colors['reset']}"
        val = f"{_value_color(confidence)}{confidence}{colors['reset']}"
        LogUtils.print(f"{tag} {prefix}{val}")

    def before_approval(tool_name, arguments):
        if tool_name not in _MUTATION_TOOLS:
            return None
        if not env_bool("MONITOR_CONFIDENCE_BEFORE_APPROVAL"):
            return None
        confidence = arguments.get("confidence")
        if confidence is not None:
            _print_confidence(confidence, prefix="before-approval: ")
        return None  # Don't affect approval decision

    def after_tool(tool_name, arguments, result):
        confidence = arguments.get("confidence")
        if confidence is not None:
            confidence = float(confidence)  # coerce for rolling-window sum
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
