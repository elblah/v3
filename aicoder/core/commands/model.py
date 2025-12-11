"""
Model command - Switch between AI models
Synchronous version
"""

from aicoder.core.commands.base import BaseCommand, CommandResult, CommandContext
from aicoder.utils.log import LogUtils, LogOptions
from aicoder.core.config import Config


class ModelCommand(BaseCommand):
    """Switch between AI models"""

    def __init__(self, context: CommandContext):
        super().__init__(context)
        self.previous_model = None

    def get_name(self) -> str:
        return "model"

    def get_description(self) -> str:
        return "Switch between AI models"

    def execute(self, args: list = None) -> CommandResult:
        """Handle model switching"""
        if not args:
            self._show_current_model()
            return CommandResult(should_quit=False)

        new_model = args[0]

        # Handle special case: back to previous model
        if new_model == "back":
            return self._switch_to_previous_model()

        return self._switch_model(new_model)

    def _show_current_model(self):
        """Show current model and available models"""
        LogUtils.print(
            f"Current model: {Config.model()}", LogOptions(color=Config.colors["cyan"])
        )
        LogUtils.print("\nAvailable models:", LogOptions(bold=True))

        # Get models from config or environment
        models = [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "gemini-pro",
        ]

        for model in models:
            if model == Config.model():
                LogUtils.print(
                    f"  {model} (current)", LogOptions(color=Config.colors["green"])
                )
            else:
                LogUtils.print(f"  {model}")

    def _switch_to_previous_model(self) -> CommandResult:
        """Switch back to previous model"""
        if not self.previous_model:
            LogUtils.warn("No previous model to switch back to")
            return CommandResult(should_quit=False)

        LogUtils.print(f"Switching back to previous model: {self.previous_model}")

        # Store current as previous
        current = Config.model()

        # This would require updating the config dynamically
        # For now, just show what would happen
        LogUtils.warn(
            "Model switching not fully implemented - would need config update"
        )

        # Update previous model
        self.previous_model = current

        return CommandResult(should_quit=False)

    def _switch_model(self, new_model: str) -> CommandResult:
        """Switch to a new model"""
        if new_model == Config.model():
            LogUtils.print(f"Already using model: {new_model}")
            return CommandResult(should_quit=False)

        # Store current model as previous
        self.previous_model = Config.model()

        LogUtils.print(f"Switching from {self.previous_model} to {new_model}")

        # This would require updating the config dynamically
        # For now, just show what would happen
        LogUtils.warn(
            "Model switching not fully implemented - would need config update"
        )

        return CommandResult(should_quit=False)


class ModelBackCommand(BaseCommand):
    """Switch back to previous model"""

    def __init__(self, context: CommandContext):
        super().__init__(context)
        self.previous_model = None

    def get_name(self) -> str:
        return "model-back"

    def get_description(self) -> str:
        return "Switch back to previous model"

    def execute(self, args: list = None) -> CommandResult:
        """Switch back to previous model"""
        if not self.previous_model:
            LogUtils.warn("No previous model to switch back to")
            return CommandResult(should_quit=False)

        LogUtils.print(f"Switching back to previous model: {self.previous_model}")

        # Store current as previous
        current = Config.model()

        # This would require updating the config dynamically
        # For now, just show what would happen
        LogUtils.warn(
            "Model switching not fully implemented - would need config update"
        )

        # Update previous model
        self.previous_model = current

        return CommandResult(should_quit=False)
