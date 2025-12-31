"""
Markdown colorization component for streaming responses.
Handles colorized output of markdown content with proper state management.
"""

from aicoder.core.config import Config


class MarkdownColorizer:
    """Handles colorized output of markdown content with proper state management"""

    def __init__(self):
        self.reset_state()

    def reset_state(self) -> None:
        """Reset all colorization state"""
        self._in_code = False
        self._code_tick_count = 0
        self._in_star = False
        self._star_count = 0
        self._at_line_start = True
        self._in_header = False
        self._in_bold = False
        self._consecutive_count = 0
        self._can_be_bold = False

    def print_with_colorization(self, content: str) -> str:
        """Process content with colorization"""
        if not content:
            return content

        result = []
        i = 0

        while i < len(content):
            char = content[i]

            # Handle consecutive asterisk counting
            if char == "*":
                self._consecutive_count += 1
                # Only allow bold for exactly 2 asterisks, not 3+
                if self._consecutive_count == 2:
                    self._can_be_bold = True
                elif self._consecutive_count > 2:
                    self._can_be_bold = False
            else:
                self._consecutive_count = 0

            # Handle newlines - reset line start and any active modes
            if char == "\n":
                self._at_line_start = True
                # Reset header mode
                if self._in_header:
                    result.append(Config.colors["reset"])
                    self._in_header = False
                # Reset star mode on newline
                if self._in_star:
                    result.append(Config.colors["reset"])
                    self._in_star = False
                    self._star_count = 0
                # Reset bold mode on newline
                if self._in_bold:
                    result.append(Config.colors["reset"])
                    self._in_bold = False
                # Reset can_be_bold on newline
                self._can_be_bold = False
                result.append(char)
                i += 1
                continue

            # Precedence 1: If we're in code mode, only look for closing backticks
            if self._in_code:
                result.append(char)
                if char == "`":
                    self._code_tick_count -= 1
                    if self._code_tick_count == 0:
                        result.append(Config.colors["reset"])
                        self._in_code = False
                i += 1
                continue

            # Precedence 2: If we're in star mode, keep current formatting and look for closing stars
            if self._in_star:
                result.append(char)  # Keep current formatting
                if char == "*":
                    self._star_count -= 1
                    if self._star_count == 0:
                        # Reset everything at the end of star sequence
                        result.append(Config.colors["reset"])
                        self._in_star = False

                        # Handle bold mode toggle
                        if self._can_be_bold:
                            if self._in_bold:
                                self._in_bold = False
                            else:
                                self._in_bold = True
                                # Apply bold after reset
                                result.append(Config.colors["bold"])

                        # Reset counters when sequence ends
                        self._consecutive_count = 0
                        self._can_be_bold = False
                i += 1
                continue

            # Precedence 3: Check for backticks (highest precedence)
            if char == "`":
                # Count consecutive backticks
                tick_count = 0
                j = i
                while j < len(content) and content[j] == "`":
                    tick_count += 1
                    j += 1

                # Start code block
                result.append(Config.colors["green"])
                result.append("`" * tick_count)
                self._in_code = True
                self._code_tick_count = tick_count
                self._at_line_start = False
                i += tick_count
                continue

            # Precedence 4: Check for asterisks (medium precedence)
            if char == "*":
                # Count consecutive asterisks
                star_count = 0
                j = i
                while j < len(content) and content[j] == "*":
                    star_count += 1
                    j += 1

                # Start star block with GREEN + BOLD (correct order)
                result.append(Config.colors["green"] + Config.colors["bold"])
                result.append("*" * star_count)

                self._in_star = True
                self._star_count = star_count
                self._at_line_start = False
                i += star_count
                continue

            # Precedence 5: Check for header # at line start (lowest precedence)
            if self._at_line_start and char == "#":
                result.append(Config.colors["red"])
                self._in_header = True
                result.append(char)
                self._at_line_start = False
                i += 1
                continue

            # Regular character
            result.append(char)
            self._at_line_start = False
            i += 1

        return "".join(result)

    def process_with_colorization(self, content: str) -> str:
        """Public method to process content with colorization"""
        return self.print_with_colorization(content)
