"""
Base command interface
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from aicoder.core.message_history import MessageHistory
from aicoder.core.input_handler import InputHandler
from aicoder.core.stats import Stats


@dataclass
class CommandContext:
    """Context provided to commands"""

    message_history: MessageHistory
    input_handler: InputHandler
    stats: Stats
    command_handler: Optional["CommandHandler"] = None


class CommandHandler(ABC):
    """Interface for command handler"""

    @abstractmethod
    def get_all_commands(self) -> Dict[str, "BaseCommand"]:
        pass


@dataclass
class CommandResult:
    """Result of command execution"""

    should_quit: bool = False
    run_api_call: bool = True
    message: Optional[str] = None


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
