"""
Command registry implementation
"""

from typing import Dict, List, Callable, Optional, Union
from bdb import BdbQuit
from .base import BaseCommand, CommandResult, CommandContext
from aicoder.utils.log import LogUtils


class SimplePluginCommand:
    """Wrapper for simple plugin command functions"""

    def __init__(self, name: str, handler: Callable, description: Optional[str] = None):
        self.name = name
        self.handler = handler
        self.description = description or f"Plugin command: {name}"

    def get_name(self) -> str:
        return self.name

    def get_description(self) -> str:
        return self.description

    def get_aliases(self) -> List[str]:
        return []

    def execute(self, args: List[str]) -> CommandResult:
        """Execute the plugin command"""
        try:
            args_str = " ".join(args)
            result = self.handler(args_str)
            if result:
                LogUtils.print(result)
            return CommandResult(should_quit=False, run_api_call=False)
        except Exception as e:
            # Handle BdbQuit (quitting debugger with 'q') gracefully
            if isinstance(e, (BdbQuit, SystemExit)):
                pass  # Silently ignore debugger quit
            else:
                LogUtils.error(f"Error executing command: {e}")
            return CommandResult(should_quit=False, run_api_call=False)


class CommandRegistry:
    """Registry for all commands"""

    def __init__(self, context: CommandContext):
        self.context = context
        self.commands: Dict[str, Union[BaseCommand, SimplePluginCommand]] = {}
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
        from .debug import DebugCommand

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
            DebugCommand(self.context),
        ]

        for command in commands:
            self.register_command(command)

    def register_command(self, command: Union[BaseCommand, SimplePluginCommand]):
        """Register a command"""
        # Create an instance to call methods on
        name = command.get_name()
        self.commands[name] = command

        # Register aliases (only for BaseCommand)
        if hasattr(command, "get_aliases"):
            for alias in command.get_aliases():
                self.aliases[alias] = name

    def get_command(self, name: str) -> Optional[Union[BaseCommand, SimplePluginCommand]]:
        """Get command by name or alias"""
        # Check if it's an alias
        actual_name = self.aliases.get(name, name)
        return self.commands.get(actual_name)

    def get_all_commands(self) -> Dict[str, Union[BaseCommand, SimplePluginCommand]]:
        """Get all registered commands"""
        return self.commands.copy()

    def register_simple_command(self, name: str, handler: Callable, description: Optional[str] = None):
        """Register a simple plugin command function"""
        # Remove leading slash if present
        name = name.lstrip("/")
        cmd = SimplePluginCommand(name, handler, description)
        self.commands[name] = cmd

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
            # Handle BdbQuit (quitting debugger with 'q') gracefully
            if isinstance(e, (BdbQuit, SystemExit)):
                pass  # Silently ignore debugger quit
            else:
                LogUtils.error(f"Error executing command: {e}")
            return CommandResult(should_quit=False, run_api_call=False)
