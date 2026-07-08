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
            effort_msg = f"Reasoning effort: {effort}"
            valid_values = Config._get_valid_reasoning_efforts()
            if valid_values:
                effort_msg += f"  (valid: {', '.join(valid_values)})"
            LogUtils.print(effort_msg, color="green", bold=True)
        elif mode == "on":
            LogUtils.info("Reasoning effort: API default (medium)")

        # Show reasoning strip (clear_thinking)
        if mode == "on":
            if clear_thinking is None:
                LogUtils.success("Reasoning strip: AUTO (preserving across turns - default for coding)")
            elif clear_thinking:
                LogUtils.info("Reasoning strip: ON (stripping reasoning from non-tool-call messages)")
            else:
                LogUtils.success("Reasoning strip: OFF (preserving all reasoning across turns)")

        # Show what will be sent
        if mode == "default":
            LogUtils.info("Model will use its default thinking behavior")
        elif mode == "on":
            extra_body = {"thinking": {"type": "enabled"}}
            if effort:
                effort_field = Config.get_effort_field()
                LogUtils.info(f'Sending top-level: {effort_field}="{effort}"')
            if clear_thinking is not None:
                LogUtils.info(f'With extra_body: {extra_body} (clear_thinking={clear_thinking})')
            else:
                LogUtils.info(f'With extra_body: {extra_body}')
        else:
            LogUtils.info('With extra_body: {"thinking": {"type": "disabled"}}')

        LogUtils.dim("Use: /thinking [default|on|off] [effort <level>] [clear <true|false>]")

    def _show_effort(self, effort: Optional[str]) -> None:
        """Show current reasoning effort level"""
        valid_values = Config._get_valid_reasoning_efforts()

        if effort:
            LogUtils.print(f"Reasoning effort: {effort}", color="green", bold=True)
        else:
            LogUtils.info("Reasoning effort: not set (API will use default)")

        if valid_values:
            LogUtils.info(f"Valid effort levels: {', '.join(valid_values)}")
        LogUtils.dim("Use: /thinking effort <level>")

    def _set_effort(self, value: str) -> None:
        """Set reasoning effort level"""
        try:
            Config.set_reasoning_effort(value)
            new_effort = Config.reasoning_effort()
            LogUtils.success(f"[*] Reasoning effort set to: {new_effort}")
            valid_values = Config._get_valid_reasoning_efforts()
            if valid_values:
                parts = []
                for v in valid_values:
                    if v == new_effort:
                        parts.append(f"{Config.colors['yellow']}{v}{Config.colors['reset']}")
                    else:
                        parts.append(v)
                LogUtils.print(f"Valid: {' '.join(parts)}", color=None)
        except ValueError as e:
            LogUtils.error(f"[*] {e}")

    def _show_clear_thinking(self, clear_thinking: Optional[bool]) -> None:
        """Show current reasoning strip setting"""
        if clear_thinking is None:
            LogUtils.info("Reasoning strip: AUTO (preserving across turns - default for coding)")
        elif clear_thinking:
            LogUtils.info("Reasoning strip: ON (stripping reasoning from non-tool-call messages)")
        else:
            LogUtils.success("Reasoning strip: OFF (preserving all reasoning across turns)")
        LogUtils.dim("Use: /thinking clear <true|false>")

    def _set_clear_thinking(self, value: str) -> None:
        """Set reasoning strip (true=strip from non-tool-call msgs, false=preserve)"""
        if value.lower() in ("true", "1", "yes", "on"):
            Config.set_clear_thinking(True)
            LogUtils.warn("[*] Reasoning strip enabled")
            LogUtils.info("Reasoning stripped from non-tool-call messages (saves bandwidth)")
        elif value.lower() in ("false", "0", "no", "off"):
            Config.set_clear_thinking(False)
            LogUtils.success("[*] Reasoning strip disabled")
            LogUtils.info("All reasoning preserved across turns (recommended for coding)")
        else:
            LogUtils.error("Invalid value. Use: /thinking clear <true|false>")

    def _show_help(self) -> None:
        """Show help for thinking command"""
        valid_values = Config._get_valid_reasoning_efforts()

        help_text = """Usage:
  /thinking [on|off|default]      Set thinking mode
  /thinking effort <level>        Set reasoning effort level (or +/++/-/--, see below)
  /thinking effort                Show current effort level
  /thinking                       Show current status
  /thinking toggle                Toggle between on/off

Examples:
  /thinking on                    Enable thinking with preserved reasoning (default for coding)
  /thinking off                   Disable thinking
  /thinking effort high           Set reasoning effort to high
  /thinking effort +              Set reasoning effort to max (last in REASONING_EFFORT_VALID)
  /thinking effort -              Set reasoning effort to min (first in REASONING_EFFORT_VALID)
  /thinking effort ++             Step up one level from current
  /thinking effort --             Step down one level from current

Environment Variables:
  THINKING=<mode>                  Set default thinking mode (default|on|off)
  REASONING_EFFORT=<level>        Set default reasoning effort
  REASONING_EFFORT_VALID=<vals>   Comma-separated valid effort levels
  CLEAR_THINKING=<true|false>     Strip reasoning from non-tool-call messages (bandwidth optimization)
"""

        if valid_values:
            help_text += f"\nValid effort levels (from REASONING_EFFORT_VALID):\n  {', '.join(valid_values)}\n"

        LogUtils.print(help_text)
