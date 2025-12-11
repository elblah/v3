"""
API Types - External Communication Contracts

This module defines all types related to external API communication, including
request/response formats, streaming data structures, and error handling.
These types represent the contracts between the AI Coder application and
external AI services.

Domain: External API communication
Responsibilities: API contracts, streaming data, error handling, usage tracking
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from .message_types import Message, MessageToolCall


@dataclass
class ApiUsage:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    prompt_tokens_details: Optional[Dict[str, Any]] = None
    completion_tokens_details: Optional[Dict[str, Any]] = None


@dataclass
class ApiRequestData:
    model: str
    messages: List[Message]
    stream: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class StreamChunkData:
    content: Optional[str] = None
    role: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class StreamChunk:
    id: Optional[str] = None
    object: Optional[str] = None
    created: Optional[int] = None
    model: Optional[str] = None
    choices: Optional[List[Dict[str, Any]]] = None
    usage: Optional[ApiUsage] = None


class UnknownError(Exception):
    """Error for unknown API responses"""

    def __init__(self, message: str):
        super().__init__(message)
        self.name = "UnknownError"


@dataclass
class ToolCall:
    id: str
    type: str
    function: MessageToolCall
