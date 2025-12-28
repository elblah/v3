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
        from .stats import StatsCommand
        from .save import SaveCommand
        from .load import LoadCommand
        from .compact import CompactCommand
        from .sandbox import SandboxCommand
        from .edit import EditCommand
        from .retry import RetryCommand
        from .memory import MemoryCommand
        from .yolo import YoloCommand
        from .detail import DetailCommand
        from .new import NewCommand

        commands = [
            HelpCommand(self.context),
            QuitCommand(self.context),
            StatsCommand(self.context),
            SaveCommand(self.context),
            LoadCommand(self.context),
            CompactCommand(self.context),
            SandboxCommand(self.context),
            EditCommand(self.context),
            RetryCommand(self.context),
            MemoryCommand(self.context),
            YoloCommand(self.context),
            DetailCommand(self.context),
            NewCommand(self.context),
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
