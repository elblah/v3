"""
AI Coder - Fast, lightweight AI-assisted development that runs anywhere
"""

from .core.aicoder import AICoder
from .core.config import Config
from .core.stats import Stats
from .core.tool_manager import ToolManager
from .core.message_history import MessageHistory

__all__ = ["AICoder", "Config", "Stats", "ToolManager", "MessageHistory"]

__version__ = "1.0.0"
