"""
Debug command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class DebugCommand(BaseCommand):
    """Toggle debug mode or trigger breakpoint"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "debug"
        self._description = "Debug mode toggle, breakpoint trigger, prompt viewer"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["dbg"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute debug command"""
        if args is None:
            args = []

        # Show status if no args
        if not args:
            return self._show_status()

        action = args[0].lower()

        # Handle breakpoint/break
        if action in ["breakpoint", "bp", "break", "b"]:
            return self._trigger_breakpoint()

        # Handle prompt display
        if action in ["prompt", "p", "system"]:
            return self._show_prompt()

        # Handle prompt rebuild
        if action in ["rebuild-prompt", "rp", "reload-prompt"]:
            return self._rebuild_prompt()

        # Handle help/status
        if action in ["help", "h", "status", "s"]:
            return self._show_help()

        # Handle on/off/toggle
        if action in ["on", "1", "enable", "true"]:
            return self._enable_debug()
        elif action in ["off", "0", "disable", "false"]:
            return self._disable_debug()
        elif action in ["toggle", "t"]:
            if Config.debug():
                return self._disable_debug()
            else:
                return self._enable_debug()

        LogUtils.error(f"Unknown subcommand: {action}")
        self._show_help()
        return CommandResult(should_quit=False, run_api_call=False)

    def _show_help(self) -> CommandResult:
        """Show detailed debug command help"""
        c = Config.colors
        status = "ENABLED" if Config.debug() else "DISABLED"
        status_color = "green" if Config.debug() else "yellow"

        subcmds = [
            ("on",             "Enable debug mode"),
            ("off",            "Disable debug mode"),
            ("toggle",         "Toggle debug mode on/off"),
            ("status",         "Show current debug status (default)"),
            ("prompt",         "Print the full system prompt sent to the AI"),
            ("rebuild-prompt", "Re-read all files and rebuild system prompt (rp, reload-prompt)"),
            ("breakpoint",     "Trigger Python breakpoint() (bp, break, b)"),
            ("help",           "Show this help message"),
        ]
        pad = max(len(n) for n, _ in subcmds) + 1

        lines = [
            f"{c['bold']}Debug Command{c['reset']}",
            f"{c['dim']}{'─' * 50}{c['reset']}",
            f"  Status: {c[status_color]}{status}{c['reset']}",
            "",
            f"{c['bold']}Usage:{c['reset']}",
            f"  /debug [subcommand]",
            "",
            f"{c['bold']}Subcommands:{c['reset']}",
        ]
        for name, desc in subcmds:
            lines.append(f"  {c['green']}{name}{c['reset']}{' ' * (pad - len(name))}{desc}")
        lines.extend([
            "",
            f"{c['bold']}Aliases:{c['reset']}",
            f"  /dbg = /debug",
        ])

        if Config.debug():
            lines.extend([
                "",
                f"{c['bold']}Current State:{c['reset']}",
                f"  {c['green']}●{c['reset']} Debug logging active — API details visible",
            ])
        else:
            lines.extend([
                "",
                f"{c['bold']}Current State:{c['reset']}",
                f"  {c['yellow']}●{c['reset']} Debug disabled — use {c['green']}/debug on{c['reset']} to enable",
            ])

        LogUtils.print("\n".join(lines))
        return CommandResult(should_quit=False, run_api_call=False)

    def _show_status(self) -> CommandResult:
        """Show current debug status"""
        return self._show_help()

    def _rebuild_prompt(self) -> CommandResult:
        """Rebuild the system prompt from scratch"""
        LogUtils.warn("[*] Rebuilding system prompt...")
        self.context.app.rebuild_system_prompt()
        return CommandResult(should_quit=False, run_api_call=False)

    def _show_prompt(self) -> CommandResult:
        """Print the current system prompt"""
        msgs = self.context.message_history.messages
        prompt = None
        for m in msgs:
            if m.get("role") == "system":
                prompt = m.get("content", "")
                break

        if not prompt:
            LogUtils.error("No system prompt found in message history")
            return CommandResult(should_quit=False, run_api_call=False)

        lines = prompt.splitlines()
        c = Config.colors
        LogUtils.print(f"{c['bold']}System Prompt ({len(lines)} lines, {len(prompt)} chars):{c['reset']}")
        LogUtils.print(f"{c['dim']}{'─' * 60}{c['reset']}")
        for i, line in enumerate(lines, 1):
            ln = f"{c['green']}{i:>4}{c['reset']}  {line}"
            LogUtils.print(ln)
        LogUtils.print(f"{c['dim']}{'─' * 60}{c['reset']}")

        return CommandResult(should_quit=False, run_api_call=False)

    def _enable_debug(self) -> CommandResult:
        """Enable debug mode"""
        if Config.debug():
            LogUtils.warn("[*] Debug mode is already enabled")
        else:
            Config.set_debug(True)
            LogUtils.success("[*] Debug mode ENABLED")
            LogUtils.info("Detailed output will now be shown for API calls")
        return CommandResult(should_quit=False, run_api_call=False)

    def _disable_debug(self) -> CommandResult:
        """Disable debug mode"""
        if Config.debug():
            Config.set_debug(False)
            LogUtils.warn("[*] Debug mode DISABLED")
            LogUtils.info("Only essential output will be shown")
        else:
            LogUtils.warn("[*] Debug mode is already disabled")
        return CommandResult(should_quit=False, run_api_call=False)

    def _trigger_breakpoint(self) -> CommandResult:
        """Trigger a Python breakpoint for debugging"""
        LogUtils.warn("\n[*] Triggering Python breakpoint()...")
        LogUtils.info("    Use 'c' to continue, 'q' to quit, or explore variables")
        LogUtils.dim("    Type 'help' for debugger commands\n")

        # Trigger the actual breakpoint
        breakpoint()

        LogUtils.success("\n[*] Breakpoint session ended")
        return CommandResult(should_quit=False, run_api_call=False)
