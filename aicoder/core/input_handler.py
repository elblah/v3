"""
Input handler for AI Coder using readline
 - synchronous version
"""

import os
import sys
import signal
from typing import List, Optional, Callable
import readline
from aicoder.core.config import Config
from aicoder.core import prompt_history


from aicoder.utils.shell_utils import ShellResult, execute_command_sync


class InputHandler:
    """
    Input handler for AI Coder using readline
    
    """

    def __init__(self, context_bar=None, stats=None, message_history=None):
        self.history: List[str] = []
        self.history_index = -1
        self.context_bar = context_bar
        self.stats = stats
        self.message_history = message_history
        self.is_interactive = sys.stdin.isatty()

        # Completer registry for plugins
        self.completers: List[Callable[[str, int], Optional[str]]] = []

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

        # Remove @ and - from word delimiters so @@snippet completion works with hyphens
        # Default delimiters: \t\n\"\\'`@$><=;|&{( (tab, newline, quote, backtick, $, @, >, <, =, ;, |, &, {, ()
        # We want to keep most but remove @ and - to allow @@prefix-hyphen to be completed as one word
        delims = readline.get_completer_delims().replace('@', '').replace('-', '')
        readline.set_completer_delims(delims)

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
        except EOFError:
            print()  # New line after Ctrl+D
            raise  # Re-raise, let caller handle it (now continues like Ctrl+C)

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
                # Get available commands including aliases
                commands = [
                    "/help",
                    "/h",
                    "/?",
                    "/quit",
                    "/stats",
                    "/save",
                    "/s",
                    "/load",
                    "/l",
                    "/memory",
                    "/new",
                    "/n",
                    "/yolo",
                    "/y",
                    "/detail",
                    "/d",
                    "/compact",
                    "/c",
                    "/sandbox-fs",
                    "/sfs",
                    "/edit",
                    "/e",
                    "/retry",
                ]

                # Filter commands that match
                options = [cmd for cmd in commands if cmd.startswith(text)]

            # Call registered completers for additional completions
            for completer in self.completers:
                try:
                    # State machine: call with state=0 to collect all matches,
                    # then iterate through states until completer returns None
                    c_state = 0
                    while True:
                        result = completer(text, c_state)
                        if result is None:
                            break
                        if result not in options:  # Avoid duplicates
                            options.append(result)
                        c_state += 1
                except Exception as e:
                    if Config.debug():
                        import warnings
                        warnings.warn(f"Completer failed: {e}")

            self.completion_matches = options

        if state < len(self.completion_matches):
            return self.completion_matches[state]
        return None

    def register_completer(self, completer: Callable[[str, int], Optional[str]]) -> None:
        """Register a completer function for Tab completion"""
        self.completers.append(completer)

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
