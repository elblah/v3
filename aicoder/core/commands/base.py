"""
Base command interface
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class CommandContext:
    """Context provided to commands - using simple class instead of dataclass to avoid ~80ms import cost"""

    __slots__ = ('message_history', 'input_handler', 'stats', 'command_handler')

    def __init__(self, message_history, input_handler, stats, command_handler=None):
        self.message_history = message_history
        self.input_handler = input_handler
        self.stats = stats
        self.command_handler = command_handler


class CommandHandler(ABC):
    """Interface for command handler"""

    @abstractmethod
    def get_all_commands(self) -> Dict[str, "BaseCommand"]:
        pass


class CommandResult:
    """Result of command execution - using simple class instead of dataclass"""

    __slots__ = ('should_quit', 'run_api_call', 'message', 'command_to_execute')

    def __init__(self, should_quit=False, run_api_call=True, message=None, command_to_execute=None):
        self.should_quit = should_quit
        self.run_api_call = run_api_call
        self.message = message
        self.command_to_execute = command_to_execute


class BaseCommand(ABC):
    """Base class for all commands"""

    def __init__(self, context: CommandContext):
        self.context = context

    @abstractmethod
    def get_name(self) -> str:
        """Get command name"""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Get command description"""
        pass

    @abstractmethod
    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute the command"""
        pass

    def get_aliases(self) -> List[str]:
        """Return aliases for this command (override in subclasses)"""
        return []
