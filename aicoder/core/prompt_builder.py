"""
Universal prompt builder system
Compatible with Python
Supports Python {variable} format and automatic AGENTS.md integration

"""

import os
import platform
import sys
from typing import Optional, Dict, Any

from aicoder.utils.log import LogUtils


class PromptContext:
    """Context for prompt building"""

    def __init__(self):
        self.current_directory = os.getcwd()
        self.current_datetime = self._get_current_datetime()
        self.system_info = self._get_system_info()
        self.agents_content = None

    def _get_current_datetime(self) -> str:
        """Get current datetime string in UTC"""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def _get_system_info(self) -> str:
        """Get system information"""
        return f"Platform: {platform.system()} ({platform.machine()}), Python: {sys.version.split()[0]}"


class PromptOptions:
    """Options for prompt building"""

    def __init__(self):
        self.override_prompt = None


class PromptBuilder:
    """Universal prompt builder for system prompts"""

    _default_prompt_template = None

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the prompt builder is initialized"""
        return cls._default_prompt_template is not None

    @classmethod
    def initialize(cls) -> None:
        """Initialize the prompt builder by loading the default template"""
        # Try package-relative path first
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "default-system-prompt.md"
        )

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                cls._default_prompt_template = f.read()
            return
        except Exception:
            # Try current directory as fallback
            template_path = "default-system-prompt.md"
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    cls._default_prompt_template = f.read()
            except Exception:
                # Use minimal fallback
                cls._default_prompt_template = """You are a helpful AI assistant.
You have access to various tools for file operations, search, and command execution.
Always follow user instructions carefully and provide helpful responses."""

    @classmethod
    def build_prompt(
        cls, context: PromptContext, options: Optional[PromptOptions] = None
    ) -> str:
        """Build the complete system prompt from template and context"""
        options = options or PromptOptions()

        # Use override if provided, otherwise use default template
        prompt = options.override_prompt or cls._default_prompt_template

        # Normalize template format to Python {variable} style
        if "${" in prompt:
            import re

            prompt = re.sub(r"\$\{([^}]+)\}", r"{\1}", prompt)

        # Replace Python-compatible variables
        prompt = prompt.replace("{current_directory}", context.current_directory)
        prompt = prompt.replace("{current_datetime}", context.current_datetime)
        prompt = prompt.replace("{system_info}", context.system_info)

        # Handle {available_tools} - for now include basic info since tools come via API
        available_tools_info = cls._get_available_tools_info()
        prompt = prompt.replace("{available_tools}", available_tools_info)

        # Replace agents content if variable exists
        agents_content = context.agents_content or ""
        prompt = prompt.replace("{agents_content}", agents_content)

        # Smart AGENTS.md handling for overrides (Option 2)
        if options.override_prompt and context.agents_content:
            has_agents_var = (
                "{agents_content}" in prompt
                or "<project_specific_instructions>" in prompt
            )

            if not has_agents_var:
                # Append AGENTS.md with proper structure
                clean_agents = context.agents_content.replace("\n\n---\n\n", "")
                prompt += (
                    "\n\n<project_specific_instructions>\n"
                    + clean_agents
                    + "\n</project_specific_instructions>"
                )
                LogUtils.info("Appended AGENTS.md to PROMPT-OVERRIDE.md")

        return prompt

    @classmethod
    def load_prompt_override(cls) -> Optional[str]:
        """Load PROMPT-OVERRIDE.md content if it exists"""
        try:
            if os.path.exists("PROMPT-OVERRIDE.md"):
                LogUtils.info("Using PROMPT-OVERRIDE.md as system prompt")
                with open("PROMPT-OVERRIDE.md", "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            # Silently ignore if PROMPT-OVERRIDE.md doesn't exist or can't be read
            pass
        return None

    @classmethod
    def load_agents_content(cls) -> Optional[str]:
        """Load AGENTS.md content if it exists"""
        try:
            if os.path.exists("AGENTS.md"):
                with open("AGENTS.md", "r", encoding="utf-8") as f:
                    return "\n\n---\n\n" + f.read()
        except Exception:
            # Silently ignore if AGENTS.md doesn't exist or can't be read
            pass
        return None

    @classmethod
    def _get_available_tools_info(cls) -> str:
        """Get basic available tools information
        Since tools are provided via API request, this is minimal info
        """
        return """Basic tools available: file operations (read, write, list),
search (grep), shell command execution, and more via API request."""

    @classmethod
    def build_system_prompt(cls) -> str:
        """Build system prompt with context information"""
        # Initialize if needed
        if not cls.is_initialized():
            cls.initialize()

        # Create context
        context = PromptContext()

        # Load additional content
        context.agents_content = cls.load_agents_content()

        # Load prompt override: env var takes precedence over file
        options = PromptOptions()
        from .config import Config

        env_prompt = Config.system_prompt()
        if env_prompt:
            LogUtils.info("Using AICODER_SYSTEM_PROMPT environment variable as system prompt")
            options.override_prompt = env_prompt
        else:
            options.override_prompt = cls.load_prompt_override()

        # Build and return prompt
        return cls.build_prompt(context, options)
