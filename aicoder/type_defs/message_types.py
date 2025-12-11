"""
Message Types - Core Domain Entities

This module defines the fundamental message and conversation types that form
the core domain model of the AI Coder application. These types represent the
primary data structures used throughout the system for communication between
the user, AI, and tools.

Domain: Core message/conversation handling
Responsibilities: Message structure, content management, conversation flow
"""

from typing import List, Optional, Dict, Any, TypedDict


class MessageRole:
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageToolCall(TypedDict):
    id: str
    type: str
    function: Dict[str, Any]
    index: Optional[int]


class Message(TypedDict):
    role: str
    content: Optional[str]
    tool_calls: Optional[List[MessageToolCall]]
    tool_call_id: Optional[str]


class AssistantMessage(TypedDict):
    content: Optional[str]
    tool_calls: Optional[List[MessageToolCall]]


class ToolResultData(TypedDict):
    tool_call_id: str
    content: str
