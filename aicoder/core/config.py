"""
Configuration module for AI Coder

"""

import os
import sys
from typing import Any, Dict, List, Optional, Set
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
    _detail_tty = os.environ.get("DETAIL_TTY") == "1"

    # Thinking mode - initialize from env var ONCE at module load time
    # After this, only runtime state is used (env var ignored)
    # Supported values: "default", "on" (1/yes/true), "off" (0/no/false)
    def _init_thinking_from_env() -> str:
        env_val = os.environ.get("THINKING", "").lower()
        if env_val in ("on", "1", "yes", "true"):
            return "on"
        elif env_val in ("off", "0", "no", "false"):
            return "off"
        return "default"

    _thinking = _init_thinking_from_env()

    # Clear thinking - initialize from env var ONCE at module load time
    # After this, only runtime state is used (env var ignored)
    # false = preserve reasoning across turns (recommended for coding)
    # true = strip reasoning from non-tool-call messages before sending (saves bandwidth)
    def _init_clear_thinking_from_env() -> Optional[bool]:
        env_val = os.environ.get("CLEAR_THINKING", "").lower()
        if env_val in ("1", "true", "yes", "on"):
            return True
        elif env_val in ("0", "false", "no", "off"):
            return False
        return None

    _clear_thinking = _init_clear_thinking_from_env()

    @staticmethod
    def clear_thinking() -> Optional[bool]:
        """
        Get reasoning strip state (true=strip from non-tool-call msgs, false=preserve, None=default)
        """
        return Config._clear_thinking

    @classmethod
    def set_clear_thinking(cls, value: bool) -> None:
        """
        Set reasoning strip state (true=strip from non-tool-call msgs, false=preserve)
        """
        cls._clear_thinking = value

    # Show reasoning - initialize from env var ONCE at module load time
    # AICODER_SHOW_REASONING=0 disables printing reasoning on first content
    # Default (unset or any other value): enabled
    _show_reasoning = os.environ.get("AICODER_SHOW_REASONING", "1").lower() not in ("0", "false", "no", "off")

    @staticmethod
    def show_reasoning() -> bool:
        """Get show_reasoning state (true=print reasoning, false=suppress)"""
        return Config._show_reasoning

    @classmethod
    def set_show_reasoning(cls, value: bool) -> None:
        """Set show_reasoning state"""
        cls._show_reasoning = value

    # Suppress error body - initialize from env var ONCE at module load time
    # After this, only runtime state is used (env var ignored)
    # false = include error body in HTTP error messages (default)
    # true = suppress error body from HTTP error messages
    _suppress_error_body = os.environ.get("AICODER_SUPPRESS_ERROR_BODY", "").lower() in ("1", "true", "yes", "on")

    @staticmethod
    def suppress_error_body() -> bool:
        """
        Get suppress_error_body state (true=hide error body, false=show error body)
        """
        return Config._suppress_error_body

    # Reasoning effort - initialize from env var ONCE at module load time
    # After this, only runtime state is used (env var ignored)
    # Valid values configurable via REASONING_EFFORT_VALID env var
    def _init_reasoning_effort_from_env() -> Optional[str]:
        env_val = os.environ.get("REASONING_EFFORT", "")
        if not env_val:
            return None
        return env_val.lower()

    _reasoning_effort = _init_reasoning_effort_from_env()

    @staticmethod
    def _get_valid_reasoning_efforts() -> Optional[Set[str]]:
        """
        Get valid reasoning effort values from env var REASONING_EFFORT_VALID
        Returns None if not set (accept any value)
        """
        env_val = os.environ.get("REASONING_EFFORT_VALID", "")
        if not env_val:
            return None
        return {v.strip().lower() for v in env_val.split(",")}

    @staticmethod
    def reasoning_effort() -> Optional[str]:
        """
        Get reasoning effort level
        """
        return Config._reasoning_effort

    @classmethod
    def set_reasoning_effort(cls, effort: Optional[str]) -> None:
        """
        Set reasoning effort level
        Validates against REASONING_EFFORT_VALID if set
        """
        if effort is not None:
            valid_values = cls._get_valid_reasoning_efforts()
            if valid_values is not None and effort.lower() not in valid_values:
                valid_list = ", ".join(sorted(valid_values))
                raise ValueError(f"Invalid reasoning effort: {effort}. Valid values: {valid_list}")
        cls._reasoning_effort = effort.lower() if effort else None

    # Reasoning format registry - maps provider to effort field name
    # Can be extended for new providers
    # Set uses_extra_body=False for providers that only need top-level reasoning_effort
    _reasoning_formats: Dict[str, Dict[str, Any]] = {
        "deepseek": {"effort_field": "reasoning_effort", "uses_extra_body": True},
        "glm": {"effort_field": "reasoning_effort", "uses_extra_body": True},
        "openai": {"effort_field": "reasoning_effort", "uses_extra_body": False},
        "anthropic": {"uses_extra_body": True},
    }

    # Model name patterns for auto-detection
    _reasoning_format_patterns: Dict[str, List[str]] = {
        "deepseek": ["deepseek"],
        "glm": ["glm", "zhipuai", "z.ai"],
        "openai": ["gpt", "o1", "o3", "o4", "chatgpt", "openai"],
        "anthropic": ["claude", "anthropic"],
    }

    @classmethod
    def get_reasoning_format(cls) -> Optional[str]:
        """
        Get reasoning format (deepseek, glm, etc.)
        Priority: 1) REASONING_FORMAT env var override, 2) auto-detect from model name
        """
        # Check env var override first
        env_format = os.environ.get("REASONING_FORMAT", "")
        if env_format:
            return env_format.lower()

        # Auto-detect from model name
        model = cls.model()
        if model:
            model_lower = model.lower()
            for fmt, patterns in cls._reasoning_format_patterns.items():
                for pattern in patterns:
                    if pattern in model_lower:
                        return fmt
        return "openai"  # default to OpenAI format if no match

    @classmethod
    def get_effort_field(cls) -> str:
        """
        Get the effort field name for current format (e.g., reasoning_effort or reasoningEffort)
        """
        fmt = cls.get_reasoning_format()
        if fmt and fmt in cls._reasoning_formats:
            field = cls._reasoning_formats[fmt].get("effort_field")
            if field:
                return field
        return "reasoning_effort"  # default

    # Default reasoning field names to check across providers
    REASONING_FIELDS_DEFAULT = ["reasoning_content", "reasoning", "thinking", "reasoning_text"]

    @staticmethod
    def get_possible_reasoning_fields() -> List[str]:
        """
        Get list of reasoning field names to check, from env var
        AICODER_REASONING_POSSIBLE_FIELDS (comma-separated) or default list.
        """
        env = os.environ.get("AICODER_REASONING_POSSIBLE_FIELDS")
        if env:
            fields = [f.strip() for f in env.split(",") if f.strip()]
            if fields:
                return fields
        return list(Config.REASONING_FIELDS_DEFAULT)

    @staticmethod
    def get_reasoning_field() -> Optional[str]:
        """
        Get reasoning field name override from env var AICODER_REASONING_FIELD.
        Returns None if not set, allowing fallback to multi-field guessing.
        When set, this field is used exclusively for read/store/send.
        """
        val = os.environ.get("AICODER_REASONING_FIELD")
        if val:
            return val.strip()
        return None

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

    @staticmethod
    def detail_tty() -> bool:
        """Get detail TTY passthrough state"""
        return Config._detail_tty

    @staticmethod
    def set_detail_tty(enabled: bool) -> None:
        """Set detail TTY passthrough state"""
        Config._detail_tty = enabled

    # Thinking mode state - initialize from env var ONCE at module load time
    # After this, only runtime state is used (env var ignored)
    # Values: "default", "on", "off"
    @staticmethod
    def thinking() -> str:
        """
        Get thinking mode state ("default", "on", or "off")
        """
        return Config._thinking

    @classmethod
    def set_thinking(cls, mode: str) -> None:
        """
        Set thinking mode state ("default", "on", or "off")
        """
        cls._thinking = mode

    @staticmethod
    def thinking_budget_tokens() -> int:
        """
        Get budget tokens for thinking mode from THINKING_BUDGET_TOKENS env var (default: 16000)
        """
        val = os.environ.get("THINKING_BUDGET_TOKENS", "")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return 16000

    @classmethod
    def thinking_extra_body(cls) -> Optional[dict]:
        """
        Get extra_body for thinking mode if configured
        Returns None for "default", otherwise returns thinking config
        Only includes thinking.type if format uses extra_body (effort goes to top level via thinking_params)
        """
        mode = cls.thinking()
        if mode == "default":
            return None
        elif mode == "off":
            return {"thinking": {"type": "disabled"}}
        elif mode == "on":
            fmt = cls.get_reasoning_format()
            if fmt and fmt in cls._reasoning_formats:
                if not cls._reasoning_formats[fmt].get("uses_extra_body", True):
                    return None  # Format doesn't use extra_body
            return {"thinking": {"type": "enabled", "budget_tokens": cls.thinking_budget_tokens()}}
        return None

    @classmethod
    def thinking_params(cls) -> Optional[dict]:
        """
        Get thinking parameters for top-level request fields (e.g., reasoning_effort for DeepSeek)
        Returns None if thinking is not "on" or no params are configured.
        Priority for field name: 1) REASONING_FIELD env override, 2) hardcoded format mapping
        """
        mode = cls.thinking()
        if mode != "on":
            return None

        params = {}
        effort = cls.reasoning_effort()
        if effort:
            # Check env override first (REASONING_FIELD / AICODER_REASONING_FIELD)
            override = cls.get_reasoning_field()
            field = override if override else cls.get_effort_field()
            params[field] = effort

        return params if params else None

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
    def retry_status_codes() -> set:
        """Get HTTP status codes that should be retried from AICODER_RETRY_STATUS_CODES env var.
        Default: {429}. Format: comma-separated codes like '429,401,502,503'"""
        raw = os.environ.get("AICODER_RETRY_STATUS_CODES", "429")
        codes = set()
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                codes.add(int(part))
        return codes or {429}

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
        Get API endpoint - supports full override via API_ENDPOINT env var
        
        """
        override = os.environ.get("API_ENDPOINT")
        if override:
            return override
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
    def system_prompt_append() -> str:
        """
        Get content to append to system prompt from environment variable.
        Appended AFTER AICODER_SYSTEM_PROMPT or default prompt.

        """
        return os.environ.get("AICODER_SYSTEM_PROMPT_APPEND") or ""

    @staticmethod
    def tools_allow() -> Optional[Set[str]]:
        """
        Get allowed tools from TOOLS_ALLOW environment variable.
        Format: comma-separated list of tool names.
        If set, only these tools will be available.

        Available internal tools:
        - read_file: Read file contents
        - write_file: Write/create files
        - edit_file: Edit files with exact text replacement
        - run_shell_command: Execute shell commands
        - grep: Search text in files
        - list_directory: List files and directories

        Example: TOOLS_ALLOW="read_file,grep,list_directory" (read-only access)

        Returns:
            Set of allowed tool names, or None if not set (all tools allowed)
        """
        env_val = os.environ.get("TOOLS_ALLOW", "").strip()
        if env_val:
            return set(name.strip() for name in env_val.split(",") if name.strip())
        return None

    @staticmethod
    def tools_deny() -> Set[str]:
        """
        Get denied tools from TOOLS_DENY environment variable.
        Format: comma-separated list of tool names.
        If set, these tools will NOT be available.

        Example: TOOLS_DENY="write_file,run_shell_command" (block write/shell access)

        Returns:
            Set of denied tool names, or empty set if not set
        """
        env_val = os.environ.get("TOOLS_DENY", "").strip()
        if env_val:
            return set(name.strip() for name in env_val.split(",") if name.strip())
        return set()

    @staticmethod
    def plugins_allow() -> Optional[Set[str]]:
        """
        Get allowed plugins from PLUGINS_ALLOW environment variable.
        Format: comma-separated list of plugin names (without .py extension).
        If set, only these plugins will be loaded.

        Example: PLUGINS_ALLOW="web,github,rag" (only load these plugins)

        Returns:
            Set of allowed plugin names, or None if not set (all plugins allowed)
        """
        env_val = os.environ.get("PLUGINS_ALLOW", "").strip()
        if env_val:
            return set(name.strip() for name in env_val.split(",") if name.strip())
        return None

    @staticmethod
    def plugins_deny() -> Set[str]:
        """
        Get denied plugins from PLUGINS_DENY environment variable.
        Format: comma-separated list of plugin names (without .py extension).
        If set, these plugins will NOT be loaded.

        Example: PLUGINS_DENY="web,github" (block these plugins from loading)

        Returns:
            Set of denied plugin names, or empty set if not set
        """
        env_val = os.environ.get("PLUGINS_DENY", "").strip()
        if env_val:
            return set(name.strip() for name in env_val.split(",") if name.strip())
        return set()

    @staticmethod
    def http_headers() -> Dict[str, str]:
        """
        Get custom HTTP headers from AICODER_HTTP_HEADERS environment variable.
        Format: "Header1: Value1\nHeader2: Value2\n"
        
        Returns:
            Dict of header name to header value
        """
        headers_str = os.environ.get("AICODER_HTTP_HEADERS", "")
        if not headers_str:
            return {}
        
        headers = {}
        for line in headers_str.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            
            # Split on first colon only
            parts = line.split(':', 1)
            if len(parts) == 2:
                header_name = parts[0].strip()
                header_value = parts[1].strip()
                if header_name and header_value:
                    headers[header_name] = header_value
        
        return headers

    @staticmethod
    def gzip_enabled() -> bool:
        """
        Check if gzip compression is enabled via AICODER_GZIP environment variable.
        Default is enabled (gzip=True). Set AICODER_GZIP=0 to disable.
        
        Returns:
            bool: True if gzip is enabled, False if disabled
        """
        return os.environ.get("AICODER_GZIP", "1") != "0"

    @staticmethod
    def streaming_enabled() -> bool:
        """
        Check if streaming is enabled via AICODER_STREAM environment variable.
        Default is enabled (streaming=True). Set AICODER_STREAM=0 to disable.
        
        Returns:
            bool: True if streaming is enabled, False if disabled
        """
        return os.environ.get("AICODER_STREAM", "1") != "0"

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

    @staticmethod
    def top_p() -> float:
        """
        Get top_p setting

        """
        top_p = os.environ.get("TOP_P")
        return float(top_p) if top_p else None

    @staticmethod
    def frequency_penalty() -> float:
        """
        Get frequency_penalty setting

        """
        freq_penalty = os.environ.get("FREQUENCY_PENALTY")
        return float(freq_penalty) if freq_penalty else None

    @staticmethod
    def presence_penalty() -> float:
        """
        Get presence_penalty setting

        """
        pres_penalty = os.environ.get("PRESENCE_PENALTY")
        return float(pres_penalty) if pres_penalty else None

    @staticmethod
    def top_k() -> int:
        """
        Get top_k setting

        """
        top_k = os.environ.get("TOP_K")
        return int(top_k) if top_k else None

    @staticmethod
    def session_file() -> str:
        """Get session JSON file path from env var (for load-on-start, save-on-exit)"""
        return os.environ.get("SESSION_JSON_FILE") or os.environ.get("AICODER_SESSION_FILE") or ""

    @staticmethod
    def session_output_file() -> str:
        """Get session output JSONL file path from env var (for AI response logging)"""
        return os.environ.get("SESSION_OUTPUT_FILE") or os.environ.get("AICODER_SESSION_OUTPUT") or ""

    @staticmethod
    def repetition_penalty() -> float:
        """
        Get repetition_penalty setting

        """
        rep_penalty = os.environ.get("REPETITION_PENALTY")
        return float(rep_penalty) if rep_penalty else None

    # Streaming Configuration
    @staticmethod
    def total_timeout() -> int:
        """
        Get total timeout in seconds

        """
        return int(os.environ.get("TOTAL_TIMEOUT", "300"))

    @staticmethod
    def total_timeout_extension() -> int:
        """
        Get timeout extension for active streaming (seconds)
        Grants extra time when data is actively flowing.
        Set to 0 to disable (hard timeout).

        """
        return int(os.environ.get("TOTAL_TIMEOUT_EXTENSION", "30"))

    # Context and Memory Configuration
    _default_context_size = int(os.environ.get("CONTEXT_SIZE", "128000"))
    _context_size = _default_context_size

    @staticmethod
    def context_size() -> int:
        """
        Get context size
        
        """
        return Config._context_size

    @staticmethod
    def default_context_size() -> int:
        """
        Get default context size (from env var)
        
        """
        return Config._default_context_size

    @staticmethod
    def set_context_size(size: int) -> None:
        """
        Set context size at runtime
        
        """
        Config._context_size = size

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
        return int(os.environ.get("MAX_TOOL_RESULT_SIZE", "20000"))

    @staticmethod
    def default_read_limit() -> int:
        """
        Get default read file limit

        """
        return int(os.environ.get("DEFAULT_READ_LIMIT", "150"))

    @staticmethod
    def default_grep_max_results() -> int:
        """
        Get default grep max results

        """
        return int(os.environ.get("DEFAULT_GREP_MAX_RESULTS", "500"))

    @staticmethod
    def default_shell_timeout() -> int:
        """
        Get default shell command timeout

        """
        return int(os.environ.get("DEFAULT_SHELL_TIMEOUT", "30"))

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
        api_provider = os.environ.get("API_PROVIDER", "").lower()
        
        if api_provider == "anthropic":
            # Anthropic uses API_ENDPOINT directly
            if not os.environ.get("API_ENDPOINT"):
                LogUtils.error("Error: Missing required environment variable:")
                LogUtils.error("  - API_ENDPOINT")
                LogUtils.print("")
                LogUtils.success("Example configuration:")
                LogUtils.success('  export API_PROVIDER=anthropic')
                LogUtils.success('  export API_ENDPOINT="https://api.minimax.io/anthropic/v1/messages"')
                LogUtils.print("")
                LogUtils.print("Optional variables:")
                LogUtils.print('  export API_KEY="your-api-key-here"')
                LogUtils.print('  export API_MODEL="your-model-name"')
                LogUtils.print("  export DEBUG=1")
                sys.exit(1)
        elif not Config.base_url():
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
            LogUtils.print('  export AICODER_SYSTEM_PROMPT_APPEND="additional-instructions"')
            sys.exit(1)

    # Print configuration info at startup
    @staticmethod
    def print_startup_info() -> None:
        """
        Print configuration info at startup

        """
        if not sys.stdout.isatty():
            return

        # Original behavior: use green for configuration messages
        LogUtils.success("Configuration:")

        # API Provider (show only if explicitly set)
        api_provider = os.environ.get("API_PROVIDER", "")
        if api_provider:
            LogUtils.success(f"  API Provider: {api_provider}")

        LogUtils.success(f"  API Endpoint: {Config.api_endpoint()}")
        LogUtils.success(f"  Model: {Config.model()}")

        if Config.debug():
            LogUtils.warn("DEBUG MODE IS ON")

        # Thinking mode
        mode = Config.thinking()
        if mode != "default":
            mode_text = f"  Thinking: {mode}"
            if mode == "on":
                effort = Config.reasoning_effort()
                if effort:
                    mode_text += f" (effort: {effort})"
                fmt = Config.get_reasoning_format()
                if fmt:
                    override = os.environ.get("REASONING_FORMAT", "")
                    suffix = ", override" if override else ""
                    mode_text += f" (format: {fmt}{suffix})"
            LogUtils.success(mode_text)

        if os.environ.get("TEMPERATURE"):
            LogUtils.success(f"  Temperature: {Config.temperature()}")

        if os.environ.get("MAX_TOKENS"):
            LogUtils.success(f"  Max tokens: {Config.max_tokens()}")

        if Config.system_prompt():
            LogUtils.success("  System prompt: overridden via AICODER_SYSTEM_PROMPT environment variable")

        if Config.system_prompt_append():
            LogUtils.success("  System prompt append: set via AICODER_SYSTEM_PROMPT_APPEND environment variable")

        if Config.auto_compact_enabled():
            LogUtils.success(
                f"  Auto-compaction enabled (context: {Config.context_size()} tokens, triggers at {Config.context_compact_percentage()}%)"
            )

        if not Config.streaming_enabled():
            LogUtils.success("  Non-streaming mode enabled")

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
