"""
Input handler for AI Coder using readline
Ported exactly from TypeScript version - synchronous version
"""

import os
import sys
from typing import List, Optional
import readline
from aicoder.core.config import Config
from aicoder.utils.log import Colors
from aicoder.core import prompt_history


from aicoder.utils.shell_utils import ShellResult, execute_command_sync


class InputHandler:
    """
    Input handler for AI Coder using readline
    Ported exactly from TS version
    """

    def __init__(self, context_bar=None, stats=None, message_history=None):
        self.history: List[str] = []
        self.history_index = -1
        self.context_bar = context_bar
        self.stats = stats
        self.message_history = message_history
        self.is_interactive = sys.stdin.isatty()

        # Only setup readline in interactive mode
        if self.is_interactive:
            self._setup_readline()

    def _setup_readline(self):
        """Setup readline with history and completion"""
        # Load history BEFORE creating readline interface
        self._load_prompt_history()

        # Set history file
        try:
            readline.read_history_file()
        except:
            pass

        # Setup completion
        readline.set_completer(self._completer)
        readline.parse_and_bind("tab: complete")

    def get_user_input(self) -> str:
        """Get user input with context display"""
        if not self.is_interactive:
            # Handle piped input
            return sys.stdin.readline() or ""

        try:
            # Show context bar before user prompt (if available)
            if self.context_bar and self.stats and self.message_history:
                self.context_bar.print_context_bar_for_user(
                    self.stats, self.message_history
                )

            # Show input prompt
            prompt = f"> "
            return input(prompt).strip()
        except KeyboardInterrupt:
            print()  # New line after Ctrl+C
            raise  # Re-raise, let caller handle it

    def _load_prompt_history(self):
        """Load prompt history"""
        try:
            entries = prompt_history.read_history()
            # Only add prompts (not commands starting with /) to readline history
            # Take only last 10 (oldest first for readline)
            self.history = [
                entry["prompt"]
                for entry in entries
                if not entry["prompt"].startswith("/")
            ][-10:]

            # Add to readline history
            for prompt in self.history:
                readline.add_history(prompt)

        except Exception as e:
            if Config.debug():
                import warnings

                warnings.warn(f"Failed to load history: {e}")

    def _completer(self, text: str, state: int) -> Optional[str]:
        """Tab completion for commands"""
        if state == 0:
            options = []

            # Only complete commands if text starts with / or is not empty
            if text.startswith("/") or text:
                # Get available commands
                commands = [
                    "/help",
                    "/quit",
                    "/stats",
                    "/save",
                    "/load",
                    "/memory",
                    "/new",
                    "/n",
                    "/e",
                ]

                # Filter commands that match
                options = [cmd for cmd in commands if cmd.startswith(text)]

            # For non-command input, could add file path completion here
            # (left as future enhancement)

            self.completion_matches = options

        if state < len(self.completion_matches):
            return self.completion_matches[state]
        return None

    def setup_signal_handlers(self):
        """Setup signal handlers for clean exit"""

        def handle_sigint(signum, frame):
            # Handle Ctrl+C gracefully
            print("\nUse /quit to exit")

        signal.signal(signal.SIGINT, handle_sigint)

    def close(self) -> None:
        """Close input handler - clean up resources"""
        # No readline cleanup needed in Python
        pass
