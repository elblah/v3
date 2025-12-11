"""
Tool Types - Tool System & CLI Interactions

This module combines tool execution system types with CLI interaction types,
as both represent user-facing functionality. The tool system handles
definition, execution, and output formatting, while CLI types manage
command-line interactions and user input/output.

Domain: Tool execution and CLI interactions
Responsibilities: Tool definitions, execution workflow, user input handling, command results
"""

from dataclasses import dataclass
from typing import Callable, Any, List, Optional, Dict, Awaitable, Union
from typing import Protocol


@dataclass
class ToolDefinition:
    type: str  # 'internal' | 'plugin'
    auto_approved: bool
    approval_excludes_arguments: bool
    description: str
    parameters: Dict[str, Any]
    execute: callable


@dataclass
class ToolParameters:
    type: str = "object"
    properties: Dict[str, Any] = None
    required: List[str] = None

    def __post_init__(self):
        if self.properties is None:
            self.properties = {}
        if self.required is None:
            self.required = []


class ToolExecutionArgs:
    def __init__(self, preview_mode: bool = False, **kwargs):
        self.preview_mode = preview_mode
        for key, value in kwargs.items():
            setattr(self, key, value)





@dataclass
class ToolPreview:
    content: str
    can_approve: bool


@dataclass
class ToolResult:
    tool_call_id: str
    friendly: str      # Always shown to users
    detailed: str      # Always sent to AI, shown to users in detail mode
    success: bool = True


# CLI & Command related types
class ReadlineInterface(Protocol):
    def prompt(self, query: str) -> str: ...
    def close(self) -> None: ...
    def set_prompt(self, prompt: str) -> None: ...
    def write(self, data: str) -> None: ...

    # Legacy interface for compatibility
    def on(self, event: str, callback: Callable) -> None: ...
    def question(self, message: str, callback: Callable[[str], None]) -> None: ...

    history: Optional[List[str]]


CompletionCallback = Union[
    Callable[[str], List[str]], Callable[[Any, Optional[List[str]]], None]
]


@dataclass
class CommandResult:
    should_quit: bool = False
    run_api_call: bool = True
    message: Optional[str] = None
