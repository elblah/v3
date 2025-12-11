"""Type definitions for AI Coder"""

from .message_types import (
    Message,
    MessageToolCall,
    AssistantMessage,
    ToolResultData,
    MessageRole,
)

from .tool_types import (
    ToolDefinition,
    ToolParameters,
    ToolExecutionArgs,
    ToolPreview,
    ToolResult,
    ReadlineInterface,
    CompletionCallback,
    CommandResult,
)

from .api_types import (
    ApiUsage,
    ApiRequestData,
    StreamChunkData,
    StreamChunk,
    UnknownError,
    ToolCall,
)

from .system_types import (
    MessageHistory,
    StreamingClient,
    InputHandler,
    Stats,
    Plugin,
    PluginContext,
    CommandHandler,
    NotificationHooks,
    PopupMenuItem,
    PopupMenuProvider,
    CouncilMember,
    CouncilConfig,
    CouncilResult,
    PromptContext,
    PromptOptions,
    ConfigValue,
    ValidationResult,
    ErrorWithMessage,
)

__all__ = [
    # Message types
    "Message",
    "MessageToolCall",
    "AssistantMessage",
    "ToolResultData",
    "MessageRole",
    # Tool types
    "ToolDefinition",
    "ToolParameters",
    "ToolExecutionArgs",
    "ToolPreview",
    "ToolResult",
    "ReadlineInterface",
    "CompletionCallback",
    "CommandResult",
    # API types
    "ApiUsage",
    "ApiRequestData",
    "StreamChunkData",
    "StreamChunk",
    "UnknownError",
    "ToolCall",
    # System types
    "MessageHistory",
    "StreamingClient",
    "InputHandler",
    "Stats",
    "Plugin",
    "PluginContext",
    "CommandHandler",
    "NotificationHooks",
    "PopupMenuItem",
    "PopupMenuProvider",
    "CouncilMember",
    "CouncilConfig",
    "CouncilResult",
    "PromptContext",
    "PromptOptions",
    "ConfigValue",
    "ValidationResult",
    "ErrorWithMessage",
]
