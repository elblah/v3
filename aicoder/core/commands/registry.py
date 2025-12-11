"""
Command registry implementation
"""

from typing import Dict, List, Callable, Any, Optional
from .base import BaseCommand, CommandResult, CommandContext
from aicoder.utils.log import LogUtils


class CommandRegistry:
    """Registry for all commands"""

    def __init__(self, context: CommandContext):
        self.context = context
        self.commands: Dict[str, BaseCommand] = {}
        self.aliases: Dict[str, str] = {}
        self._register_all_commands()

    def _register_all_commands(self):
        """Register all built-in commands"""
        from .help import HelpCommand
        from .quit import QuitCommand
        from .clear import ClearCommand
        from .stats import StatsCommand
        from .save import SaveCommand
        from .load import LoadCommand
        from .compact import CompactCommand
        from .sandbox import SandboxCommand
        from .council import CouncilCommand
        from .edit import EditCommand
        from .model import ModelCommand, ModelBackCommand
        from .retry import RetryCommand
        from .memory import MemoryCommand
        from .snippets import SnippetsCommand
        from .yolo import YoloCommand
        from .detail import DetailCommand
        from .reset import ResetCommand

        commands = [
            HelpCommand(self.context),
            QuitCommand(self.context),
            ClearCommand(self.context),
            StatsCommand(self.context),
            SaveCommand(self.context),
            LoadCommand(self.context),
            CompactCommand(self.context),
            SandboxCommand(self.context),
            CouncilCommand(self.context),
            EditCommand(self.context),
            ModelCommand(self.context),
            ModelBackCommand(self.context),
            RetryCommand(self.context),
            MemoryCommand(self.context),
            SnippetsCommand(self.context),
            YoloCommand(self.context),
            DetailCommand(self.context),
            ResetCommand(self.context),
        ]

        for command in commands:
            self.register_command(command)

    def register_command(self, command: BaseCommand):
        """Register a command"""
        # Create an instance to call methods on
        name = command.get_name()
        self.commands[name] = command

        # Register aliases
        for alias in command.get_aliases():
            self.aliases[alias] = name

    def register_plugin_command(
        self,
        name: str,
        handler: Callable[[List[str]], bool | None],
        description: str = "Plugin command",
    ):
        """Register a plugin command with a simple handler function"""
        # Strip leading slash if present
        cmd_name = name.lstrip("/")

        # Create a simple wrapper command class
        class PluginCommand(BaseCommand):
            def __init__(
                self, context: CommandContext, handler_func: Callable, desc: str
            ):
                super().__init__(context)
                self._handler = handler_func
                self._desc = desc
                self._name = cmd_name

            def get_name(self) -> str:
                return self._name

            def get_description(self) -> str:
                return self._desc

            def execute(self, args: List[str] = None) -> CommandResult:
                try:
                    result = self._handler(args or [])
                    if result is None:
                        result = False
                    return CommandResult(should_quit=bool(result), run_api_call=False)
                except Exception as e:
                    LogUtils.error(f"Plugin command error: {e}")
                    return CommandResult(should_quit=False, run_api_call=False)

        # Register plugin command
        self.register_command(PluginCommand(self.context, handler, description))

    def get_command(self, name: str) -> Optional[BaseCommand]:
        """Get command by name or alias"""
        # Check if it's an alias
        actual_name = self.aliases.get(name, name)
        return self.commands.get(actual_name)

    def get_all_commands(self) -> Dict[str, BaseCommand]:
        """Get all registered commands"""
        return self.commands.copy()

    def list_commands(self) -> List[Dict[str, str]]:
        """List all commands with their descriptions"""
        return [
            {
                "name": cmd.get_name(),
                "description": cmd.get_description(),
                "aliases": cmd.get_aliases(),
            }
            for cmd in self.commands.values()
        ]

    def execute_command(self, command_line: str) -> CommandResult:
        """Execute a command line"""
        # Parse command line
        parts = command_line.strip().split()
        if not parts:
            return CommandResult(should_quit=False, run_api_call=False)

        # Remove leading slash if present
        command_name = parts[0].lstrip("/")
        args = parts[1:] if len(parts) > 1 else []

        # Get command
        command = self.get_command(command_name)
        if not command:
            LogUtils.error(f"Unknown command: {command_line}")
            return CommandResult(should_quit=False, run_api_call=False)

        # Execute command
        try:
            return command.execute(args)
        except Exception as e:
            LogUtils.error(f"Error executing command: {e}")
            return CommandResult(should_quit=False, run_api_call=False)
