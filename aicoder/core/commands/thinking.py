"""
Thinking command implementation
"""

from typing import List, Optional
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class ThinkingCommand(BaseCommand):
    """Control thinking mode for models that support it"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "thinking"
        self._description = "Control thinking mode (default/on/off)"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute thinking command"""
        current_mode = Config.thinking()
        current_effort = Config.reasoning_effort()
        current_clear_thinking = Config.clear_thinking()

        if not args:
            self._show_status(current_mode, current_effort, current_clear_thinking)
            return CommandResult(should_quit=False, run_api_call=False)

        action = args[0].lower()

        if action == "effort":
            if len(args) >= 2:
                self._set_effort(args[1])
            else:
                self._show_effort(current_effort)
            return CommandResult(should_quit=False, run_api_call=False)

        if action == "clear":
            if len(args) >= 2:
                self._set_clear_thinking(args[1])
            else:
                self._show_clear_thinking(current_clear_thinking)
            return CommandResult(should_quit=False, run_api_call=False)
            if len(args) >= 2:
                self._set_effort(args[1])
            else:
                self._show_effort(current_effort)
            return CommandResult(should_quit=False, run_api_call=False)

        if action == "default":
            if current_mode == "default":
                LogUtils.warn("[*] Thinking is already set to default")
            else:
                Config.set_thinking("default")
                LogUtils.success("[*] Thinking set to default")
                LogUtils.info("Model will use its default thinking behavior")
        elif action in ("on", "1", "enable", "true"):
            if current_mode == "on":
                LogUtils.warn("[*] Thinking is already enabled")
            else:
                Config.set_thinking("on")
                LogUtils.success("[*] Thinking ENABLED")
                LogUtils.info("Sending thinking enabled in API requests")
        elif action in ("off", "0", "disable", "false"):
            if current_mode == "off":
                LogUtils.warn("[*] Thinking is already disabled")
            else:
                Config.set_thinking("off")
                LogUtils.warn("[*] Thinking DISABLED")
                LogUtils.info("Sending thinking disabled in API requests")
        elif action == "toggle":
            # Toggle between on and off
            if current_mode == "on":
                Config.set_thinking("off")
                LogUtils.warn("[*] Thinking DISABLED")
                LogUtils.info("Sending thinking disabled in API requests")
            elif current_mode == "off":
                Config.set_thinking("on")
                LogUtils.success("[*] Thinking ENABLED")
                LogUtils.info("Sending thinking enabled in API requests")
            else:
                # If default, turn it on
                Config.set_thinking("on")
                LogUtils.success("[*] Thinking ENABLED")
                LogUtils.info("Sending thinking enabled in API requests")
        else:
            self._show_help()

        return CommandResult(should_quit=False, run_api_call=False)

    def _show_status(self, mode: str, effort: Optional[str], clear_thinking: Optional[bool]) -> None:
        """Show current thinking and reasoning effort status"""
        # Show thinking mode
        if mode == "default":
            status = "default (not controlling behavior, using API defaults)"
            status_color = "yellow"
        elif mode == "on":
            status = "on (explicitly enabled)"
            status_color = "green"
        else:
            status = "off (explicitly disabled)"
            status_color = "brightRed"

        LogUtils.print(f"Thinking: {status}", color=status_color, bold=True)

        # Show reasoning effort
        if effort:
            LogUtils.print(f"Reasoning effort: {effort}", color="green", bold=True)
        elif mode == "on":
            LogUtils.info("Reasoning effort: API default (medium)")

        # Show clear_thinking (preserve reasoning)
        if mode == "on":
            if clear_thinking is None:
                LogUtils.success("Reasoning preservation: AUTO (preserving across turns - default for coding)")
            elif clear_thinking:
                LogUtils.info("Reasoning preservation: OFF (clearing between turns)")
            else:
                LogUtils.success("Reasoning preservation: ON (preserving across turns)")

        # Show what will be sent
        if mode == "default":
            LogUtils.info("Model will use its default thinking behavior")
        elif mode == "on":
            extra_body = {"thinking": {"type": "enabled"}}
            if effort:
                extra_body["thinking"]["reasoning_effort"] = effort
            # Default to preserving reasoning
            extra_body["thinking"]["clear_thinking"] = clear_thinking if clear_thinking is not None else False
            LogUtils.info(f'Sending extra_body: {extra_body}')
        else:
            LogUtils.info('Sending extra_body: {"thinking": {"type": "disabled"}}')

        LogUtils.dim("Use: /thinking [default|on|off] [effort <level>] [clear <true|false>]")

    def _show_effort(self, effort: Optional[str]) -> None:
        """Show current reasoning effort level"""
        valid_values = Config._get_valid_reasoning_efforts()

        if effort:
            LogUtils.print(f"Reasoning effort: {effort}", color="green", bold=True)
        else:
            LogUtils.info("Reasoning effort: not set (API will use default)")

        if valid_values:
            LogUtils.info(f"Valid effort levels: {', '.join(sorted(valid_values))}")
        LogUtils.dim("Use: /thinking effort <level>")

    def _set_effort(self, value: str) -> None:
        """Set reasoning effort level"""
        try:
            Config.set_reasoning_effort(value)
            LogUtils.success(f"[*] Reasoning effort set to: {value}")
        except ValueError as e:
            LogUtils.error(f"[*] {e}")

    def _show_clear_thinking(self, clear_thinking: Optional[bool]) -> None:
        """Show current clear_thinking setting"""
        if clear_thinking is None:
            LogUtils.info("Reasoning preservation: AUTO (preserving across turns - default for coding)")
        elif clear_thinking:
            LogUtils.info("Reasoning preservation: OFF (clearing between turns)")
        else:
            LogUtils.success("Reasoning preservation: ON (preserving across turns)")
        LogUtils.dim("Use: /thinking clear <true|false>")

    def _set_clear_thinking(self, value: str) -> None:
        """Set clear_thinking (true=clear reasoning, false=preserve reasoning)"""
        if value.lower() in ("true", "1", "yes", "on"):
            Config.set_clear_thinking(True)
            LogUtils.warn("[*] Clear thinking enabled (reasoning not preserved)")
            LogUtils.info("Use this for faster/cheaper simple queries")
        elif value.lower() in ("false", "0", "no", "off"):
            Config.set_clear_thinking(False)
            LogUtils.success("[*] Preserved thinking enabled")
            LogUtils.info("Reasoning will be preserved across turns (recommended for coding)")
        else:
            LogUtils.error("Invalid value. Use: /thinking clear <true|false>")

    def _show_help(self) -> None:
        """Show help for thinking command"""
        valid_values = Config._get_valid_reasoning_efforts()

        help_text = """Usage:
  /thinking [on|off|default]      Set thinking mode
  /thinking effort <level>        Set reasoning effort level
  /thinking effort                Show current effort level
  /thinking clear <true|false>    Set reasoning preservation (false=preserve, true=clear)
  /thinking clear                 Show current reasoning preservation setting
  /thinking                       Show current status
  /thinking toggle                Toggle between on/off

Examples:
  /thinking on                    Enable thinking with preserved reasoning (default for coding)
  /thinking off                   Disable thinking
  /thinking effort high           Set reasoning effort to high
  /thinking clear false           Enable preserved thinking (recommended for coding)
  /thinking clear true            Clear reasoning between turns (faster/cheaper)

Environment Variables:
  THINKING=<mode>                  Set default thinking mode (default|on|off)
  REASONING_EFFORT=<level>        Set default reasoning effort
  REASONING_EFFORT_VALID=<vals>   Comma-separated valid effort levels
  CLEAR_THINKING=<true|false>     Set reasoning preservation (false=preserve, true=clear)
"""

        if valid_values:
            help_text += f"\nValid effort levels (from REASONING_EFFORT_VALID):\n  {', '.join(sorted(valid_values))}\n"

        LogUtils.print(help_text)
