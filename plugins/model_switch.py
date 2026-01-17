"""
Model Switch Plugin for AI Coder v3

Provides /model and /mb commands to switch between AI models using an external selector.

Requirements:
- Set AICODER_MODELS_BIN env var to path of model selector script
- Selector should output key=value pairs on stdout (one per line)
- Example: API_MODEL=gpt-4, API_KEY=xxx, CONTEXT_SIZE=128000

Commands:
- /model or /mc - Switch to a new model using external selector
- /model help - Show detailed help and current configuration
- /model info - Show current and previous model information
- /mb - Toggle back to previous model
"""

import os
import subprocess
import threading
from typing import Dict, Optional, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aicoder.core.plugin_system import PluginContext

# Model-related variables that need to be reset when switching
MODEL_VARIABLES = [
    'API_MODEL', 'OPENAI_MODEL',
    'API_KEY', 'OPENAI_API_KEY',
    'API_BASE_URL', 'OPENAI_BASE_URL',
    'TEMPERATURE', 'MAX_TOKENS', 'TOP_K', 'TOP_P',
    'CONTEXT_SIZE',
    'FREQUENCY_PENALTY', 'PRESENCE_PENALTY', 'STOP_SEQUENCES',
    'SEED', 'MODEL_TYPE', 'PROVIDER', 'REGION', 'DEPLOYMENT_ID'
]

# Module-level state for previous config (closure-based storage)
_previous_config: Dict[str, str] = {}
_previous_config_lock = threading.Lock()


def _get_current_config() -> Dict[str, str]:
    """Get current model configuration from environment"""
    config: Dict[str, str] = {}
    for key in MODEL_VARIABLES:
        value = os.environ.get(key)
        if value:
            config[key] = value
    return config


def _get_previous_config() -> Dict[str, str]:
    """Get previous model configuration"""
    with _previous_config_lock:
        return _previous_config.copy()


def _set_previous_config(config: Dict[str, str]) -> None:
    """Set previous model configuration"""
    with _previous_config_lock:
        global _previous_config
        _previous_config = config.copy()


def _reset_model_variables() -> None:
    """Reset all model-related environment variables"""
    for key in MODEL_VARIABLES:
        if key in os.environ:
            del os.environ[key]


def _apply_config(config: Dict[str, str]) -> None:
    """Apply configuration to environment"""
    for key, value in config.items():
        if value and value.strip():
            os.environ[key] = value


def _execute_selector(bin_path: str) -> tuple[int, str, str]:
    """Execute the external model selector binary"""
    try:
        proc = subprocess.Popen(
            [bin_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(timeout=30)
        return proc.returncode, stdout.strip(), stderr.strip()
    except subprocess.TimeoutExpired:
        proc.kill()
        return 1, '', 'Timeout expired'
    except Exception as e:
        return 1, '', str(e)


def _parse_config_output(output: str) -> Dict[str, str]:
    """Parse key=value pairs from selector output"""
    config: Dict[str, str] = {}
    for line in output.split('\n'):
        line = line.strip()
        if line and '=' in line:
            key, *value_parts = line.split('=', 1)
            value = '='.join(value_parts).strip()
            if key:
                config[key] = value
    return config


def _format_config_item(key: str, value: str) -> str:
    """Format a single config item for display"""
    from aicoder.core.config import Config
    return f"  {Config.colors['cyan']}{key}{' ' * (20 - len(key))}= {Config.colors['green']}{value}{Config.colors['reset']}"


def _handle_model_command(args_str: str) -> Optional[str]:
    """Handle /model command"""
    from aicoder.utils.log import LogUtils, LogOptions
    from aicoder.core.config import Config

    args = args_str.strip().split() if args_str.strip() else []

    # Handle subcommands
    if args and args[0] == 'help':
        _show_detailed_help()
        return None
    if args and args[0] == 'info':
        _show_model_info()
        return None

    bin_path = os.environ.get('AICODER_MODELS_BIN')
    if not bin_path:
        _show_help()
        return None

    # Debug: show the path being used
    LogUtils.print(f"Using selector: {bin_path}", LogOptions(color=Config.colors["dim"]))

    # Check if file exists
    if not os.path.exists(bin_path):
        LogUtils.error(f"Selector not found: {bin_path}")
        return None

    # Check if executable
    if not os.access(bin_path, os.X_OK):
        LogUtils.error(f"Selector not executable: {bin_path}")
        return None

    # Execute selector
    exit_code, stdout, stderr = _execute_selector(bin_path)

    LogUtils.print(f"Selector exit code: {exit_code}", LogOptions(color=Config.colors["dim"]))
    LogUtils.print(f"Selector stdout: {stdout[:100] if stdout else '(empty)'}", LogOptions(color=Config.colors["dim"]))
    if stderr:
        LogUtils.print(f"Selector stderr: {stderr}", LogOptions(color=Config.colors["red"]))

    if exit_code != 0:
        LogUtils.warn("Model selection cancelled or failed")
        return None

    if not stdout:
        LogUtils.warn("No model configuration received")
        return None

    # Parse new config
    new_config = _parse_config_output(stdout)
    if not new_config:
        LogUtils.warn("No model configuration received")
        return None

    # Take atomic snapshot of current environment
    current_config = _get_current_config()

    # Reset ALL model variables first
    _reset_model_variables()

    # Apply new config
    _apply_config(new_config)

    # Store previous config
    _set_previous_config(current_config)

    # Show result
    model_name = new_config.get('API_MODEL') or new_config.get('OPENAI_MODEL') or 'unknown'
    LogUtils.success(f"Switched to model: {model_name}")
    return None


def _handle_model_back_command(args_str: str) -> Optional[str]:
    """Handle /mb command - toggle back to previous model"""
    from aicoder.utils.log import LogUtils

    previous_config = _get_previous_config()

    if not previous_config:
        LogUtils.warn("No previous model to toggle back to")
        return None

    # Take snapshot of current for next toggle
    current_config = _get_current_config()

    # Reset and restore
    _reset_model_variables()
    _apply_config(previous_config)
    _set_previous_config(current_config)

    model_name = previous_config.get('API_MODEL') or previous_config.get('OPENAI_MODEL') or 'unknown'
    LogUtils.success(f"Toggled back to model: {model_name}")
    return None


def _show_help() -> None:
    """Show basic help"""
    from aicoder.utils.log import LogUtils, LogOptions
    from aicoder.core.config import Config

    LogUtils.print("Model Switch Configuration", LogOptions(color=Config.colors["yellow"], bold=True))
    LogUtils.print("")
    LogUtils.print("To use model switching, set the AICODER_MODELS_BIN environment variable:", LogOptions(color=Config.colors["white"]))
    LogUtils.print("  export AICODER_MODELS_BIN=\"/path/to/your/model-selector\"", LogOptions(color=Config.colors["green"]))
    LogUtils.print("")
    LogUtils.print("This should be a script or binary that:", LogOptions(color=Config.colors["white"]))
    LogUtils.print("  - Presents a model selection interface (fzf, etc.)", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  - Returns key=value pairs on stdout (one per line)", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  - Exits with code 0 on success, non-zero on cancellation", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("")
    LogUtils.print("Example output:", LogOptions(color=Config.colors["cyan"]))
    LogUtils.print("  API_MODEL=gpt-4", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  API_KEY=your-key-here", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  TEMPERATURE=0.7", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("")
    LogUtils.print("Commands:", LogOptions(color=Config.colors["cyan"]))
    LogUtils.print("  /model or /mc   - Change model", LogOptions(color=Config.colors["green"]))
    LogUtils.print("  /model help     - Show detailed help and current configuration", LogOptions(color=Config.colors["green"]))
    LogUtils.print("  /model info     - Show current and previous model information", LogOptions(color=Config.colors["green"]))
    LogUtils.print("  /mb             - Toggle back to previous model", LogOptions(color=Config.colors["green"]))
    LogUtils.print("")
    LogUtils.print("Note:", LogOptions(color=Config.colors["yellow"]))
    LogUtils.print("When switching models, all model-specific configuration variables are reset to prevent", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("state pollution between different model types and configurations.", LogOptions(color=Config.colors["dim"]))


def _show_detailed_help() -> None:
    """Show detailed help with current and previous config"""
    from aicoder.utils.log import LogUtils, LogOptions
    from aicoder.core.config import Config

    current_config = _get_current_config()
    previous_config = _get_previous_config()

    LogUtils.print("Model Command Detailed Help", LogOptions(color=Config.colors["yellow"], bold=True))
    LogUtils.print("")

    # Available variables
    LogUtils.print("Available Model Variables:", LogOptions(color=Config.colors["cyan"]))
    for var in MODEL_VARIABLES:
        LogUtils.print(f"  {var}", LogOptions(color=Config.colors["cyan"]))
    LogUtils.print("")

    # Current config
    LogUtils.print("Current Model Configuration:", LogOptions(color=Config.colors["cyan"]))
    if current_config:
        for key, value in sorted(current_config.items()):
            display_value = value[:8] + '...' if (key in ('API_KEY', 'OPENAI_API_KEY') and len(value) > 8) else value
            LogUtils.print(f"  {key} = {display_value}", LogOptions(color=Config.colors["green"]))
    else:
        LogUtils.print("  No model configuration currently set", LogOptions(color=Config.colors["yellow"]))
    LogUtils.print("")

    # Previous config
    LogUtils.print("Previous Model Configuration:", LogOptions(color=Config.colors["cyan"]))
    if previous_config:
        for key, value in sorted(previous_config.items()):
            display_value = value[:8] + '...' if (key in ('API_KEY', 'OPENAI_API_KEY') and len(value) > 8) else value
            LogUtils.print(f"  {key} = {display_value}", LogOptions(color=Config.colors["green"]))
    else:
        LogUtils.print("  No previous model configuration available", LogOptions(color=Config.colors["yellow"]))
    LogUtils.print("")

    # Commands
    LogUtils.print("Available Commands:", LogOptions(color=Config.colors["cyan"]))
    LogUtils.print("  /model or /mc   - Switch to a new model using external selector", LogOptions(color=Config.colors["green"]))
    LogUtils.print("  /model help     - Show this detailed help", LogOptions(color=Config.colors["green"]))
    LogUtils.print("  /model info     - Show current and previous model information", LogOptions(color=Config.colors["green"]))
    LogUtils.print("  /mb             - Toggle back to previous model", LogOptions(color=Config.colors["green"]))
    LogUtils.print("")

    # Setup instructions
    LogUtils.print("Setup Instructions:", LogOptions(color=Config.colors["cyan"]))
    LogUtils.print("To use model switching, set the AICODER_MODELS_BIN environment variable:", LogOptions(color=Config.colors["white"]))
    LogUtils.print("  export AICODER_MODELS_BIN=\"/path/to/your/model-selector\"", LogOptions(color=Config.colors["green"]))
    LogUtils.print("")
    LogUtils.print("The model selector should:", LogOptions(color=Config.colors["white"]))
    LogUtils.print("  - Present a model selection interface (fzf, etc.)", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  - Return key=value pairs on stdout (one per line)", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  - Exit with code 0 on success, non-zero on cancellation", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("")
    LogUtils.print("Example Output from Model Selector:", LogOptions(color=Config.colors["cyan"]))
    LogUtils.print("  API_MODEL=gpt-4", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  API_KEY=your-key-here", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  TEMPERATURE=0.7", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("  MAX_TOKENS=4096", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("")
    LogUtils.print("Note:", LogOptions(color=Config.colors["yellow"]))
    LogUtils.print("When switching models, all model-specific configuration variables are reset to prevent", LogOptions(color=Config.colors["dim"]))
    LogUtils.print("state pollution between different model types and configurations.", LogOptions(color=Config.colors["dim"]))


def _show_model_info() -> None:
    """Show current and previous model information"""
    from aicoder.utils.log import LogUtils, LogOptions
    from aicoder.core.config import Config

    current_config = _get_current_config()
    previous_config = _get_previous_config()

    LogUtils.print("Model Information", LogOptions(color=Config.colors["yellow"], bold=True))
    LogUtils.print("")

    # Current config
    LogUtils.print("Current Model Configuration:", LogOptions(color=Config.colors["cyan"]))
    if current_config:
        for key, value in sorted(current_config.items()):
            display_value = value[:8] + '...' if (key in ('API_KEY', 'OPENAI_API_KEY') and len(value) > 8) else value
            LogUtils.print(f"  {key} = {display_value}", LogOptions(color=Config.colors["green"]))
    else:
        LogUtils.print("  No model configuration currently set", LogOptions(color=Config.colors["yellow"]))
    LogUtils.print("")

    # Previous config
    LogUtils.print("Previous Model Configuration:", LogOptions(color=Config.colors["cyan"]))
    if previous_config:
        for key, value in sorted(previous_config.items()):
            display_value = value[:8] + '...' if (key in ('API_KEY', 'OPENAI_API_KEY') and len(value) > 8) else value
            LogUtils.print(f"  {key} = {display_value}", LogOptions(color=Config.colors["green"]))
    else:
        LogUtils.print("  No previous model configuration available", LogOptions(color=Config.colors["yellow"]))


def create_plugin(ctx: 'PluginContext') -> Optional[Dict[str, Callable]]:
    """Create the model switch plugin"""
    from aicoder.utils.log import LogUtils, LogOptions
    from aicoder.core.config import Config

    # Register commands
    ctx.register_command('model', _handle_model_command, 'Switch AI model using external selector')
    ctx.register_command('mc', _handle_model_command, 'Alias for /model command')
    ctx.register_command('mb', _handle_model_back_command, 'Toggle back to previous model')

    if Config.debug():
        LogUtils.print("[+] model_switch plugin loaded", LogOptions(color=Config.colors["green"]))
        LogUtils.print("  - /model or /mc - Switch model using external selector", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print("  - /model help   - Show detailed help", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print("  - /model info   - Show current/previous model info", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print("  - /mb           - Toggle back to previous model", LogOptions(color=Config.colors["cyan"]))

    return None
