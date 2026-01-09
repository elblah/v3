"""
Command Completer Plugin - Tab completion for /commands

Features:
- Tab completion with / prefix
- Automatically includes all registered commands (built-in and plugin)
- Includes command aliases
"""

from typing import Optional


def create_plugin(ctx):
    """
    Create command completer plugin

    ctx.app provides access to all components:
    - ctx.app.command_handler: Access to CommandRegistry
    - ctx.app.input_handler: Register completers
    """

    def command_completer(text: str, state: int) -> Optional[str]:
        """
        Completer function for command completion

        Activates when text starts with /
        Uses readline state machine pattern: state=0 to init, state>0 to iterate
        """
        # Only activate for / prefix
        if not text.startswith("/"):
            return None

        if state == 0:
            options = []

            # Get all commands from registry
            if ctx.app and ctx.app.command_handler:
                commands = ctx.app.command_handler.get_all_commands()

                # Add primary commands with / prefix
                for cmd_name in commands.keys():
                    options.append(f"/{cmd_name}")

                # Add aliases with / prefix
                aliases = ctx.app.command_handler.registry.aliases
                for alias in aliases.keys():
                    if alias not in commands:  # Avoid duplicates
                        options.append(f"/{alias}")

            # Filter commands that match the prefix
            filtered = [cmd for cmd in options if cmd.startswith(text)]

            # Store for iteration
            command_completer.matches = sorted(filtered)

        # Return the appropriate match based on state
        if hasattr(command_completer, 'matches') and state < len(command_completer.matches):
            return command_completer.matches[state]
        return None

    # Register completer (let PluginSystem handle the checks)
    ctx.register_completer(command_completer)

    # No cleanup needed
    return None
