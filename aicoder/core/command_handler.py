"""
Command handler for AI Coder
"""

from typing import Dict
from .commands.base import CommandContext, CommandResult, BaseCommand
from .commands.registry import CommandRegistry
from .message_history import MessageHistory
from .input_handler import InputHandler
from .stats import Stats


class CommandHandler:
    """Command handler for AI Coder"""

    def __init__(
        self, message_history: MessageHistory, input_handler: InputHandler, stats: Stats
    ):
        # Create context first, then set command_handler reference
        self.context = CommandContext(message_history, input_handler, stats)
        self.registry = CommandRegistry(self.context)
        # Set the command_handler reference in context after creation
        self.context.command_handler = self

    def handle_command(self, command: str) -> CommandResult:
        """Handle a command"""
        return self.registry.execute_command(command)

    def get_all_commands(self) -> Dict[str, "BaseCommand"]:
        """Get all registered commands"""
        return self.registry.get_all_commands()
