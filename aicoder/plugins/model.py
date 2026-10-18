"""
Show the active model.

Commands:
  /model   — Print the active model name
"""

from aicoder.core.config import Config


def _handle_model(args_str: str) -> str:
    """Handle /model — one-line model name"""
    return f"model: {Config.model() or 'unknown'}"


def create_plugin(ctx):
    """Print the active model name with /model"""

    # A local/global plugin (loaded before bundled ones) may already own /model,
    # e.g. the model_switch example — don't override it.
    plugin_system = getattr(ctx.app, "plugin_system", None)
    taken = getattr(plugin_system, "commands", None) or {}
    if "model" in taken or "/model" in taken:
        return {}

    ctx.register_command("model", _handle_model, "Print the active model name")
    return {}
