"""
System Types - Application Interfaces & Cross-Cutting Concerns

This module contains system-level interfaces, plugin types, and forward
declarations needed to break circular dependencies. It serves as the
coordination layer for different system components and provides the
infrastructure for extensibility and system integration.

Domain: System infrastructure and cross-cutting concerns
Responsibilities: Plugin system, AI councils, prompt building, forward declarations, utilities

Note: Contains forward declarations to break circular dependencies between core modules.
Each forward declaration documents the interface contract without creating direct imports.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable, Awaitable, Union, Protocol
from .message_types import Message, AssistantMessage, ToolResultData
from .api_types import ApiUsage
from .tool_types import CommandResult


# ============================================================================
# FORWARD DECLARATIONS - Break circular dependencies
# ============================================================================


class MessageHistory(Protocol):
    def add_system_message(self, content: str) -> None: ...
    def add_user_message(self, content: str) -> None: ...
    def add_assistant_message(self, message: AssistantMessage) -> None: ...
    def add_tool_results(self, results: List[ToolResultData]) -> None: ...
    def get_messages(self) -> List[Message]: ...
    def should_auto_compact(self) -> bool: ...
    def compact_memory(self) -> None: ...
    def set_api_client(self, client: "StreamingClient") -> None: ...


class StreamingClient(Protocol):
    def stream_request(self, messages: List[Message]) -> Any: ...
    def reset_colorizer(self) -> None: ...
    def process_with_colorization(self, content: str) -> str: ...
    def update_token_stats(self, usage: ApiUsage) -> None: ...


class InputHandler(Protocol):
    def get_user_input(self) -> str: ...
    def prompt(self, message: str) -> str: ...
    def add_to_history(self, input_text: str) -> None: ...
    def close(self) -> None: ...
    def set_stats_context(self, stats: "Stats") -> None: ...
    def set_message_history(self, history: MessageHistory) -> None: ...


class Stats(Protocol):
    def set_last_user_prompt(self, prompt: str) -> None: ...
    def increment_tokens_used(self, count: int) -> None: ...
    def increment_api_calls(self) -> None: ...
    def increment_tool_calls(self) -> None: ...
    def print_stats(self) -> None: ...


# ============================================================================
# PLUGIN TYPES - Plugin system
# ============================================================================


@dataclass
class Plugin:
    name: str
    version: str
    initialize: Callable[["PluginContext"], Union[None, Awaitable[None]]]
    destroy: Optional[Callable[[], Union[None, Awaitable[None]]]] = None


@dataclass
class PluginContext:
    config: Any
    register_command: Callable[
        [str, Callable[[List[str]], Awaitable[CommandResult]], Optional[str]], None
    ]
    add_user_message: Callable[[str], None]
    add_system_message: Callable[[str], None]
    get_config: Callable[[str], Optional[str]]
    set_config: Callable[[str, str], None]
    original_write_file: Callable[[str, str], Awaitable[None]]
    original_edit_file: Callable[[str, str, str], Awaitable[None]]
    app: Dict[str, Any]
    register_notify_hooks: Callable[["NotificationHooks"], None]
    register_popup_menu_item: Callable[["PopupMenuItem"], None]
    unregister_popup_menu_item: Callable[[str], None]


CommandHandler = Callable[[List[str]], Awaitable[CommandResult]]


@dataclass
class NotificationHooks:
    on_before_user_prompt: Optional[Callable[[], Union[None, Awaitable[None]]]] = None
    on_after_user_prompt: Optional[Callable[[], Union[None, Awaitable[None]]]] = None
    on_before_approval_prompt: Optional[Callable[[], Union[None, Awaitable[None]]]] = (
        None
    )
    on_after_approval_prompt: Optional[Callable[[], Union[None, Awaitable[None]]]] = (
        None
    )


HookName = str


# ============================================================================
# POPUP MENU TYPES - Dynamic popup menu items
# ============================================================================


@dataclass
class PopupMenuItem:
    label: str
    key: str
    handler: Callable[[], Union[None, Awaitable[None]]]


@dataclass
class PopupMenuProvider:
    get_menu_items: Callable[[], List[PopupMenuItem]]


# ============================================================================
# COUNCIL TYPES - AI expert system
# ============================================================================


@dataclass
class CouncilMember:
    name: str
    system_prompt: str
    vote_weight: Optional[float] = None


@dataclass
class CouncilConfig:
    members: List[CouncilMember]
    moderator_prompt: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


@dataclass
class CouncilResult:
    consensus_message: str
    voting_details: List[Dict[str, str]]


# ============================================================================
# PROMPT TYPES - Prompt building
# ============================================================================


@dataclass
class PromptContext:
    agents_content: Optional[str] = None
    current_directory: Optional[str] = None
    current_datetime: Optional[str] = None
    system_info: Optional[str] = None


@dataclass
class PromptOptions:
    override_prompt: Optional[str] = None


# ============================================================================
# UTILITY TYPES - Common utilities
# ============================================================================

ConfigValue = Union[str, int, bool, None, None]


@dataclass
class ValidationResult:
    valid: bool
    error: Optional[str] = None


class ErrorWithMessage(Exception):
    message: str

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
