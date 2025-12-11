"""
Command handler for AI Coder
"""

from .commands.base import CommandContext, CommandResult
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

    def register_command(self, name: str, handler, description: str = ""):
        """Register a new command dynamically"""
        self.registry.register_plugin_command(name, handler, description)

    def get_all_commands(self):
        """Get all commands (for plugin system)"""
        return self.registry.get_all_commands()
