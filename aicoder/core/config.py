"""
Configuration module for AI Coder

"""

import os
import sys
from aicoder.utils.log import LogUtils


class Config:
    """
    Configuration module for AI Coder
    
    """

    # ANSI Colors for terminal output - exact match
    colors = {
        "reset": "\x1b[0m",
        "bold": "\x1b[1m",
        "dim": "\x1b[2m",
        "black": "\x1b[30m",
        "red": "\x1b[31m",
        "green": "\x1b[32m",
        "yellow": "\x1b[33m",
        "blue": "\x1b[34m",
        "magenta": "\x1b[35m",
        "cyan": "\x1b[36m",
        "white": "\x1b[37m",
        "brightGreen": "\x1b[92m",
        "brightRed": "\x1b[91m",
        "brightYellow": "\x1b[93m",
        "brightBlue": "\x1b[94m",
        "brightMagenta": "\x1b[95m",
        "brightCyan": "\x1b[96m",
        "brightWhite": "\x1b[97m",
    }

    # YOLO mode state - initialize from env var ONCE at module load time
    # After this, only runtime state is used (env var ignored)
    _yolo_mode = os.environ.get("YOLO_MODE") == "1"

    @staticmethod
    def yolo_mode() -> bool:
        """
        Get YOLO mode state
        
        """
        # Environment variable only affects initial state (set at module load)
        # After initialization, only runtime state is used
        return Config._yolo_mode

    @staticmethod
    def get_yolo_mode() -> bool:
        """
        Get YOLO mode state (backward compatibility)
        
        """
        # Environment variable only affects initial state (set at module load)
        # After initialization, only runtime state is used
        return Config._yolo_mode

    @staticmethod
    def set_yolo_mode(enabled: bool) -> None:
        """
        Set YOLO mode state
        
        """
        Config._yolo_mode = enabled

    # Sandbox and detail mode state - initialize from env var ONCE at module load time
    # After this, only runtime state is used (env var ignored)
    _sandbox_disabled = os.environ.get("MINI_SANDBOX") == "0"
    _detail_mode = os.environ.get("DETAIL") == "1"

    @staticmethod
    def detail_mode() -> bool:
        """
        Get detail mode state
        """
        return Config._detail_mode

    @staticmethod
    def get_detail_mode() -> bool:
        """
        Get detail mode state (backward compatibility)
        """
        return Config._detail_mode

    @classmethod
    def set_detail_mode(cls, enabled: bool) -> None:
        """
        Set detail mode state
        """
        cls._detail_mode = enabled

    # Retry Configuration
    _runtime_max_retries = None
    _runtime_max_backoff = None

    @staticmethod
    def max_retries() -> int:
        """Get max retry attempts from environment"""
        return int(os.environ.get("MAX_RETRIES", "10"))

    @staticmethod
    def effective_max_retries() -> int:
        """Get effective max retries (runtime override or environment)"""
        if Config._runtime_max_retries is not None:
            return Config._runtime_max_retries
        return Config.max_retries()

    @classmethod
    def set_runtime_max_retries(cls, value: int | None) -> None:
        """Set runtime max retry override"""
        cls._runtime_max_retries = value

    @staticmethod
    def max_backoff() -> int:
        """Get max backoff seconds from environment"""
        return int(os.environ.get("MAX_BACKOFF_SECONDS", "64"))

    @staticmethod
    def effective_max_backoff() -> int:
        """Get effective max backoff (runtime override or environment)"""
        if Config._runtime_max_backoff is not None:
            return Config._runtime_max_backoff
        return Config.max_backoff()

    @classmethod
    def set_runtime_max_backoff(cls, value: int | None) -> None:
        """Set runtime max backoff override"""
        cls._runtime_max_backoff = value

    @staticmethod
    def sandbox_disabled() -> bool:
        """
        Check if sandbox is disabled

        """
        # Environment variable only affects initial state (set at module load)
        # After initialization, only runtime state is used
        return Config._sandbox_disabled

    @staticmethod
    def set_sandbox_disabled(disabled: bool) -> None:
        """
        Set sandbox disabled state

        """
        Config._sandbox_disabled = disabled

    # API Configuration
    @staticmethod
    def api_key() -> str:
        """
        Get API key
        
        """
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY") or ""

    @staticmethod
    def base_url() -> str:
        """
        Get base URL
        
        """
        return os.environ.get("OPENAI_BASE_URL") or os.environ.get("API_BASE_URL") or ""

    @staticmethod
    def api_endpoint() -> str:
        """
        Get API endpoint
        
        """
        base = Config.base_url()
        return f"{base}/chat/completions" if base else ""

    @staticmethod
    def model() -> str:
        """
        Get model name

        """
        return os.environ.get("OPENAI_MODEL") or os.environ.get("API_MODEL") or ""

    @staticmethod
    def system_prompt() -> str:
        """
        Get system prompt override from environment variable
        Takes precedence over PROMPT-OVERRIDE.md file

        """
        return os.environ.get("AICODER_SYSTEM_PROMPT") or ""

    @staticmethod
    def temperature() -> float:
        """
        Get temperature setting
        
        """
        temp = os.environ.get("TEMPERATURE")
        return float(temp) if temp else None

    @staticmethod
    def max_tokens():
        """
        Get max tokens setting
        
        """
        max_tokens = os.environ.get("MAX_TOKENS")
        return int(max_tokens) if max_tokens else None

    # Streaming Configuration
    @staticmethod
    def streaming_timeout() -> int:
        """
        Get streaming timeout
        
        """
        return int(os.environ.get("STREAMING_TIMEOUT", "300"))

    @staticmethod
    def streaming_read_timeout() -> int:
        """
        Get streaming read timeout
        
        """
        return int(os.environ.get("STREAMING_READ_TIMEOUT", "30"))

    @staticmethod
    def total_timeout() -> int:
        """
        Get total timeout in milliseconds
        
        """
        return int(os.environ.get("TOTAL_TIMEOUT", "300")) * 1000

    # Context and Memory Configuration
    @staticmethod
    def context_size() -> int:
        """
        Get context size
        
        """
        return int(os.environ.get("CONTEXT_SIZE", "128000"))

    @staticmethod
    def context_compact_percentage() -> int:
        """
        Get context compact percentage
        
        """
        return int(os.environ.get("CONTEXT_COMPACT_PERCENTAGE", "0"))

    @staticmethod
    def auto_compact_threshold() -> int:
        """
        Get auto compact threshold
        
        """
        percentage = Config.context_compact_percentage()
        if percentage > 0:
            capped_percentage = min(percentage, 100)
            return int(Config.context_size() * (capped_percentage / 100))
        return 0

    @staticmethod
    def auto_compact_enabled() -> bool:
        """
        Check if auto compact is enabled
        
        """
        return Config.auto_compact_threshold() > 0

    @staticmethod
    def tmux_prune_percentage() -> int:
        """
        Get tmux prune percentage
        
        """
        return int(os.environ.get("TMUX_PRUNE_PERCENTAGE", "50"))

    # Compaction Configuration
    @staticmethod
    def compact_protect_rounds() -> int:
        """
        Get compact protect rounds
        
        """
        return int(os.environ.get("COMPACT_PROTECT_ROUNDS", "2"))

    @staticmethod
    def min_summary_length() -> int:
        """
        Get minimum summary length
        
        """
        return int(os.environ.get("MIN_SUMMARY_LENGTH", "100"))

    @staticmethod
    def force_compact_size() -> int:
        """
        Get force compact size
        
        """
        return int(os.environ.get("FORCE_COMPACT_SIZE", "5"))

    # Tool Configuration
    @staticmethod
    def max_tool_result_size() -> int:
        """
        Get max tool result size
        
        """
        return int(os.environ.get("MAX_TOOL_RESULT_SIZE", "300000"))

    # Default directories to ignore when listing files
    DEFAULT_IGNORE_DIRS = [
        '.git',
        '__pycache__',
        '.ruff_cache',
        '.pytest_cache',
        '.aicoder',
        'node_modules',
        '.egg-info',
        '.dist-info',
        '.tox',
        '.venv',
        'venv',
        '.mypy_cache',
        '.hg',
        '.svn',
    ]

    # Default file patterns to ignore (matched with endswith)
    DEFAULT_IGNORE_PATTERNS = [
        '.pyc',
        '.pyo',
        '.DS_Store',
        '._',
        '*~',
        '.*.swp',
    ]

    @staticmethod
    def ignore_dirs() -> list:
        """
        Get directories to ignore when listing files.
        Returns default ignore dirs plus any user-specified via AICODER_IGNORE_DIRS.
        """
        env_value = os.environ.get('AICODER_IGNORE_DIRS', '')
        if not env_value:
            return Config.DEFAULT_IGNORE_DIRS

        user_dirs = [d.strip() for d in env_value.split(',') if d.strip()]
        return Config.DEFAULT_IGNORE_DIRS + user_dirs

    @staticmethod
    def ignore_patterns() -> list:
        """
        Get file patterns to ignore when listing files.
        Returns default patterns plus any user-specified via AICODER_IGNORE_PATTERNS.
        """
        env_value = os.environ.get('AICODER_IGNORE_PATTERNS', '')
        if not env_value:
            return Config.DEFAULT_IGNORE_PATTERNS

        user_patterns = [p.strip() for p in env_value.split(',') if p.strip()]
        return Config.DEFAULT_IGNORE_PATTERNS + user_patterns

    # Debug and Development - initialize from env var ONCE at module load time
    _debug_enabled = os.environ.get("DEBUG") == "1"

    @staticmethod
    def debug() -> bool:
        """
        Check if debug mode is enabled

        """
        # Environment variable only affects initial state (set at module load)
        # After initialization, only runtime state is used
        return Config._debug_enabled

    @classmethod
    def set_debug(cls, enabled: bool) -> None:
        """
        Set debug mode state

        """
        cls._debug_enabled = enabled

    # No fallbacks - use only configured provider
    @staticmethod
    def fallback_configs():
        """
        Get fallback configurations
        
        """
        return []

    # Validate required configuration
    @staticmethod
    def validate_config() -> None:
        """
        Validate required configuration
        
        """
        if not Config.base_url():
            LogUtils.error("Error: Missing required environment variable:")
            LogUtils.error("  - API_BASE_URL or OPENAI_BASE_URL")
            LogUtils.print("")
            LogUtils.success("Example configuration:")
            LogUtils.success('  export API_BASE_URL="https://your-api-provider.com/v1"')
            LogUtils.print("")
            LogUtils.print("Optional variables:")
            LogUtils.print('  export API_KEY="your-api-key-here" (optional, some providers don\'t require it)')
            LogUtils.print('  export API_MODEL="your-model-name" (optional, some providers have a default)')
            LogUtils.print("  export TEMPERATURE=0.0")
            LogUtils.print("  export MAX_TOKENS=4096")
            LogUtils.print("  export DEBUG=1")
            LogUtils.print('  export AICODER_SYSTEM_PROMPT="your-custom-prompt"')
            sys.exit(1)

    # Print configuration info at startup
    @staticmethod
    def print_startup_info() -> None:
        """
        Print configuration info at startup
        
        """
        LogUtils.print(f"{Config.colors['green']}Configuration:{Config.colors['reset']}")
        LogUtils.print(
            f"{Config.colors['green']}  API Endpoint: {Config.api_endpoint()}{Config.colors['reset']}"
        )
        LogUtils.print(
            f"{Config.colors['green']}  Model: {Config.model()}{Config.colors['reset']}"
        )

        if Config.debug():
            LogUtils.print(f"{Config.colors['yellow']}DEBUG MODE IS ON{Config.colors['reset']}")

        if os.environ.get("TEMPERATURE"):
            LogUtils.print(
                f"{Config.colors['green']}  Temperature: {Config.temperature()}{Config.colors['reset']}"
            )

        if os.environ.get("MAX_TOKENS"):
            LogUtils.print(
                f"{Config.colors['green']}  Max tokens: {Config.max_tokens()}{Config.colors['reset']}"
            )

        if Config.system_prompt():
            LogUtils.print(
                f"{Config.colors['green']}  System prompt: overridden via AICODER_SYSTEM_PROMPT environment variable{Config.colors['reset']}"
            )

        if Config.auto_compact_enabled():
            LogUtils.print(
                f"{Config.colors['green']}  Auto-compaction enabled (context: {Config.context_size()} tokens, triggers at {Config.context_compact_percentage()}%){Config.colors['reset']}"
            )

    @staticmethod
    def reset() -> None:
        """
        Reset all runtime state to defaults (for testing)

        """
        Config._yolo_mode = os.environ.get("YOLO_MODE") == "1"
        Config._sandbox_disabled = os.environ.get("MINI_SANDBOX") == "0"
        Config._detail_mode = os.environ.get("DETAIL") == "1"
        Config._debug_enabled = os.environ.get("DEBUG") == "1"

    @staticmethod
    def in_tmux() -> bool:
        """
        Check if running in tmux
        
        """
        return bool(os.environ.get("TMUX_PANE"))

    @staticmethod
    def socket_only() -> bool:
        """
        Check if running in socket-only mode (no readline input)
        When true, AI Coder only responds to socket commands
        """
        return os.environ.get("AICODER_SOCKET_ONLY") == "1"
