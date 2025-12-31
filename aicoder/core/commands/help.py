"""
Help command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class HelpCommand(BaseCommand):
    """Show help message for all available commands"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "help"
        self._description = "Show this help message"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["?", "h"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Display help for all commands"""
        # Get commands from command handler
        command_handler = self.context.command_handler
        if not command_handler:
            LogUtils.error("Error: Command handler not available")
            return CommandResult(should_quit=False, run_api_call=False)

        commands = command_handler.get_all_commands()
        command_names = list(commands.keys())

        # Sort commands alphabetically (skip help itself)
        sorted_names = [name for name in command_names if name != "help"]
        sorted_names.sort()

        # Build all command entries first to calculate alignment
        command_entries = []

        # Add help command entry
        help_aliases = self.get_aliases()
        help_alias_str = ""
        if help_aliases:
            help_alias_str = f" (alias: {', '.join(['/' + a for a in help_aliases])})"
        command_entries.append({
            "name": self.get_name(),
            "alias_str": help_alias_str,
            "description": self.get_description()
        })

        # Add all other commands
        for name in sorted_names:
            command = commands.get(name)
            if not command:
                continue

            # Get command details dynamically
            cmd_name = (
                command.get_name()
                if hasattr(command, "get_name")
                and callable(getattr(command, "get_name"))
                else name
            )
            description = (
                command.get_description()
                if hasattr(command, "get_description")
                and callable(getattr(command, "get_description"))
                else "Unknown command"
            )
            aliases = (
                command.get_aliases()
                if hasattr(command, "get_aliases")
                and callable(getattr(command, "get_aliases"))
                else []
            )

            alias_str = ""
            if aliases:
                alias_str = f" (alias: {', '.join(['/' + a for a in aliases])})"

            command_entries.append({
                "name": cmd_name,
                "alias_str": alias_str,
                "description": description
            })

        # Calculate maximum width for command + alias (excluding colors)
        max_width = 0
        for entry in command_entries:
            width = len(f"/{entry['name']}{entry['alias_str']}")
            max_width = max(max_width, width)

        # Sort all entries alphabetically (help will now be in proper position)
        command_entries.sort(key=lambda x: x['name'])

        # Format command lines with aligned dashes
        command_lines = []
        for entry in command_entries:
            # Calculate padding needed for this entry
            cmd_full = f"/{entry['name']}{entry['alias_str']}"
            padding = " " * (max_width - len(cmd_full) + 2)  # +2 for spacing before "-"
            line = f"  {Config.colors['green']}{cmd_full}{Config.colors['reset']}{padding}- {entry['description']}"
            command_lines.append(line)

        command_list = "\n".join(command_lines)

        help_text = f"""
{Config.colors["bold"]}Available Commands:{Config.colors["reset"]}
{command_list}
"""

        LogUtils.print(help_text)
        return CommandResult(should_quit=False, run_api_call=False)
