"""Confidence monitoring plugin.

When MONITOR_CONFIDENCE_LEVEL=1:
- Injects optional `confidence` param (0-10) into run_shell_command schema
- Adds system prompt instruction telling the AI to self-score
- Prints [confidence:N] to terminal on each run_shell_command call

Vet/tmux capture-pane scrapes [confidence:N] for auditing.
"""

import copy
import os


_SYSTEM_INSTRUCTION = """
## Confidence self-assessment
For every `run_shell_command`, include a `confidence` parameter (0-10):
0=completely guessing, 5=moderately sure, 10=absolutely certain.
Be honest. This is used for quality monitoring.
"""


def create_plugin(ctx):
    if os.environ.get("MONITOR_CONFIDENCE_LEVEL") != "1":
        return

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

    def after_tool(tool_name, arguments, result):
        if tool_name != "run_shell_command":
            return
        confidence = arguments.get("confidence")
        if confidence is not None:
            print(f"[confidence:{confidence}]")

    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)
    ctx.register_hook("modify_tool_definitions", modify_tool_definitions)
    ctx.register_hook("after_single_tool_execution", after_tool)
