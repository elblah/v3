"""
Context bar component for displaying context usage
Ported exactly from TypeScript version
"""

from datetime import datetime
from typing import Optional

from aicoder.core.config import Config


class ContextBar:
    """Context bar component for displaying context usage"""

    def __init__(self):
        pass

    def format_context_bar(self, stats, message_history) -> str:
        """
        Format the context bar with colored progress bar
        """
        # Context size is automatically updated when messages are added
        current_tokens = stats.current_prompt_size or 0
        max_tokens = Config.context_size()

        # Guard against invalid values that could cause Infinity or NaN
        percentage = 0
        if max_tokens > 0 and current_tokens and max_tokens:
            percentage = (current_tokens / max_tokens) * 100
            # Cap at reasonable values to prevent display issues
            if percentage > 999:
                percentage = 999

        percentage_str = f"{percentage:.0f}" if percentage else "0"

        # Format progress bar
        progress_bar = self.create_progress_bar(percentage)

        # Format current tokens (in k if large)
        current_tokens_str = (
            f"{current_tokens / 1000:.1f}k"
            if current_tokens > 1000
            else str(current_tokens)
        )

        max_tokens_str = (
            f"{max_tokens / 1000:.1f}k" if max_tokens > 1000 else str(max_tokens)
        )

        # Get model name (from environment or default)
        model = Config.model() or "unknown"
        model_short = (
            model.split("/")[-1] if "/" in model else model
        )  # Take last part of model path

        # Build the base context bar (not dimmed)
        context_bar = f"Context: {progress_bar} {percentage_str}% ({current_tokens_str}/{max_tokens_str} @{model_short})"

        # Add time at the end if provided (dimmed)
        time_str = self.get_current_hour()
        if time_str:
            return f"{context_bar}{Config.colors['dim']} - {time_str}{Config.colors['reset']}"

        return f"{context_bar}{Config.colors['reset']}"

    def get_current_hour(self) -> Optional[str]:
        """Get current hour string"""
        now = datetime.now()
        return now.strftime("%H:%M:%S")

    def create_progress_bar(self, percentage: float) -> str:
        """Create a colored progress bar based on percentage"""
        bar_width = 10

        # Guard against invalid percentage values (Infinity, NaN, negative)
        safe_percentage = max(0, min(100, percentage or 0))

        filled_chars = round((safe_percentage / 100) * bar_width)
        empty_chars = max(0, bar_width - filled_chars)

        # Choose color based on percentage
        if safe_percentage <= 30:
            color = Config.colors["green"]
        elif safe_percentage <= 80:
            color = Config.colors["yellow"]
        else:
            color = Config.colors["red"]

        # Guard against negative values for repeat
        safe_filled_chars = max(0, filled_chars)
        safe_empty_chars = max(0, empty_chars)

        # Use unicode block characters for progress bar
        filled_bar = "█" * safe_filled_chars
        empty_bar = "░" * safe_empty_chars

        return f"{color}{filled_bar}{Config.colors['dim']}{empty_bar}{Config.colors['reset']}"

    def print_context_bar(self, stats, message_history) -> None:
        """Print context bar (for AI prompt)"""
        context_bar = self.format_context_bar(stats, message_history)
        print(context_bar)

    def print_context_bar_for_user(self, stats, message_history) -> None:
        """Print context bar for user prompt (with newline before)"""
        context_bar = self.format_context_bar(stats, message_history)
        print(f"\n{context_bar}")
