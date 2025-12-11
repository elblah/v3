#!/usr/bin/env python3

"""
Message injector for testing AI Coder without SSE complexity.

This class allows injecting messages directly into the AI Coder processing pipeline,
bypassing the Server-Sent Events stream processing while using the exact same
tool execution logic as in normal operation.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from aicoder.core.aicoder import AICoder
from aicoder.type_defs.message_types import AssistantMessage as AICoderAssistantMessage


@dataclass
class ToolCall:
    """Represents a tool call from AI response."""
    id: str
    function_name: str
    arguments: Dict[str, Any]


@dataclass 
class AssistantMessage:
    """Represents an assistant message with optional tool calls."""
    content: str
    tool_calls: Optional[List[ToolCall]] = None


class MessageInjector:
    """
    Injects messages into AI Coder as if they came from SSE processing.
    
    This bypasses the streaming complexity while using the exact same
    tool execution pipeline as normal operation.
    """
    
    def __init__(self, aicoder: AICoder):
        self.aicoder = aicoder
        self.executed_tools: List[Dict[str, Any]] = []
    
    def inject_assistant_message(self, message: AssistantMessage) -> List[Dict[str, Any]]:
        """
        Inject an assistant message and execute any tool calls.
        
        Args:
            message: Assistant message with optional tool calls
            
        Returns:
            List of tool execution results
        """
        self.executed_tools.clear()
        
        # Create AssistantMessage TypedDict for message_history
        assistant_msg = AICoderAssistantMessage(
            content=message.content,
            tool_calls=[]
        )
        
        # Add tool calls if present
        if message.tool_calls:
            tool_calls = []
            for tool_call in message.tool_calls:
                # Convert to the format expected by AssistantMessage
                tool_calls.append({
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function_name,
                        "arguments": tool_call.arguments
                    }
                })
            assistant_msg["tool_calls"] = tool_calls
            
        # Add to message history using proper method
        self.aicoder.message_history.add_assistant_message(assistant_msg)
        
        # Execute tools if present
        if message.tool_calls:
            return self._execute_tool_calls(tool_calls if 'tool_calls' in locals() else [])
        
        return []
    
    def inject_tool_calls(self, tool_calls: List[ToolCall]) -> List[Dict[str, Any]]:
        """
        Inject tool calls directly without message content.
        
        Args:
            tool_calls: List of tool calls to execute
            
        Returns:
            List of tool execution results
        """
        self.executed_tools.clear()
        
        # Convert to internal format
        internal_tool_calls = []
        for tool_call in tool_calls:
            internal_tool_calls.append({
                "id": tool_call.id,
                "type": "function", 
                "function": {
                    "name": tool_call.function_name,
                    "arguments": tool_call.arguments
                }
            })
        
        # Create AssistantMessage TypedDict
        assistant_message = AICoderAssistantMessage(
            content="",
            tool_calls=internal_tool_calls
        )
        
        # Add to message history using proper method
        self.aicoder.message_history.add_assistant_message(assistant_message)
        
        # Execute tools
        return self._execute_tool_calls(internal_tool_calls)
    
    def _execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute tool calls using AI Coder's tool execution pipeline.
        
        Args:
            tool_calls: Internal format tool calls
            
        Returns:
            List of tool execution results
        """
        results = []
        
        try:
            # Use the tool executor directly
            if hasattr(self.aicoder, 'tool_executor'):
                self.aicoder.tool_executor.execute_tool_calls(tool_calls)
                
                # Since execute_tool_calls doesn't return results directly,
                # we need to capture them from the execution process
                # For now, we'll return a placeholder to indicate execution happened
                for tool_call in tool_calls:
                    results.append({
                        "tool_call_id": tool_call.get("id", ""),
                        "success": True,
                        "content": "Tool executed"
                    })
            else:
                raise RuntimeError("Tool executor not available")
                
        except Exception as e:
            # Capture execution errors
            error_result = {
                "tool_call_id": tool_calls[0]["id"] if tool_calls else "unknown",
                "error": f"Tool execution failed: {str(e)}",
                "success": False
            }
            results.append(error_result)
        
        # Store executed tools for verification
        self.executed_tools.extend(results)
        
        return results
    
    def get_executed_tools(self) -> List[Dict[str, Any]]:
        """Get list of all executed tools from the last injection."""
        return self.executed_tools.copy()
    
    def reset(self) -> None:
        """Reset injector state."""
        self.executed_tools.clear()
    
    def create_write_file_call(self, tool_id: str, path: str, content: str) -> ToolCall:
        """Create a write_file tool call for testing."""
        return ToolCall(
            id=tool_id,
            function_name="write_file",
            arguments={"path": path, "content": content}
        )
    
    def create_edit_file_call(self, tool_id: str, path: str, old_string: str, new_string: str) -> ToolCall:
        """Create an edit_file tool call for testing."""
        return ToolCall(
            id=tool_id,
            function_name="edit_file", 
            arguments={
                "path": path,
                "old_string": old_string,
                "new_string": new_string
            }
        )
    
    def create_read_file_call(self, tool_id: str, path: str, offset: int = 0, limit: int = 2000) -> ToolCall:
        """Create a read_file tool call for testing."""
        return ToolCall(
            id=tool_id,
            function_name="read_file",
            arguments={"path": path, "offset": offset, "limit": limit}
        )


# Utility functions for creating test scenarios
class TestScenarios:
    """Predefined test scenarios for safety mechanism testing."""
    
    @staticmethod
    def write_file_without_reading(tool_id: str = "test_1", path: str = "test.txt", content: str = "test content") -> List[ToolCall]:
        """Scenario: AI tries to write file without reading it first."""
        return [ToolCall(
            id=tool_id,
            function_name="write_file",
            arguments={"path": path, "content": content}
        )]
    
    @staticmethod
    def read_then_write_file(tool_id_1: str = "test_1", tool_id_2: str = "test_2", 
                           path: str = "test.txt", content: str = "test content") -> List[ToolCall]:
        """Scenario: AI reads file then writes to it (should work)."""
        return [
            ToolCall(
                id=tool_id_1,
                function_name="read_file", 
                arguments={"path": path}
            ),
            ToolCall(
                id=tool_id_2,
                function_name="write_file",
                arguments={"path": path, "content": content}
            )
        ]
    
    @staticmethod
    def edit_file_without_reading(tool_id: str = "test_1", path: str = "test.txt", 
                                old: str = "old", new: str = "new") -> List[ToolCall]:
        """Scenario: AI tries to edit file without reading it first."""
        return [ToolCall(
            id=tool_id,
            function_name="edit_file",
            arguments={"path": path, "old_string": old, "new_string": new}
        )]