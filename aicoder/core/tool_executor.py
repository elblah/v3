"""
Tool Executor - Handles tool execution, approval, and display
Extracted from AICoder class for better separation of concerns
"""

import json
from typing import Dict, Any, List, Union

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils, LogOptions
from aicoder.core.tool_formatter import ToolFormatter
from aicoder.type_defs.tool_types import ToolExecutionArgs


class ToolExecutor:
    """Handles tool execution, approval, and result display"""

    def __init__(self, tool_manager, message_history):
        self.tool_manager = tool_manager
        self.message_history = message_history

    def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> None:
        """Execute multiple tool calls with approval and display"""
        if not tool_calls:
            return
        
        

        try:
            tool_results = []

            for tool_call in tool_calls:
                result = self._execute_single_tool_call(tool_call)
                if result:
                    tool_results.append(result)

            # Add all tool results to message history
            self.message_history.add_tool_results(tool_results)

        except Exception as e:
            LogUtils.error(f"Tool execution error: {e}")

    def _execute_single_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single tool call and return result"""
        tool_name = tool_call.get("function", {}).get("name")
        if not tool_name:
            return None

        # Get tool definition
        tool_def = self.tool_manager.tools.get(tool_name)
        if not tool_def:
            return self._handle_tool_not_found(tool_name, tool_call.get("id", ""))

        # Parse arguments
        arguments = self._parse_tool_arguments(tool_call.get("function", {}).get("arguments", "{}"))

        # Display tool info
        LogUtils.print(
            f"\n[*] Tool: {tool_name}",
            LogOptions(color=Config.colors["yellow"], bold=True),
        )

        # Generate and display preview
        if self._should_show_preview(tool_def, arguments):
            result = self._handle_preview_display(tool_def, arguments, tool_call.get("id", ""))
            if result is False:
                return None  # Preview was rejected without message
            elif isinstance(result, dict):
                # Safety violation or error - return directly to AI
                return result

        # Show formatted arguments if no preview
        elif tool_def and tool_def.get("formatArguments"):
            formatted_args = tool_def["formatArguments"](arguments)
            if formatted_args:
                LogUtils.print(formatted_args, LogOptions(color=Config.colors["cyan"]))

        # Check approval
        if not self._get_tool_approval(tool_name):
            return {
                "tool_call_id": tool_call.get("id", ""),
                "content": "Tool execution cancelled by user",
            }

        # Execute tool
        return self._execute_tool(tool_name, arguments, tool_call.get("id", ""))

    def _parse_tool_arguments(self, args_str: str) -> Dict[str, Any]:
        """Parse tool arguments from string"""
        try:
            if isinstance(args_str, dict):
                return args_str
            else:
                return json.loads(args_str)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _handle_tool_not_found(self, tool_name: str, tool_call_id: str) -> Dict[str, Any]:
        """Handle case where tool is not found"""
        LogUtils.error(f"[x] Tool not found: {tool_name}")
        self.message_history.add_system_message(
            f"Error: Tool '{tool_name}' does not exist."
        )
        return {
            "tool_call_id": tool_call_id,
            "content": f"Error: Tool '{tool_name}' does not exist.",
        }

    def _should_show_preview(self, tool_def: Dict[str, Any], arguments: Dict[str, Any]) -> bool:
        """Check if preview should be shown"""
        # Force True for testing write_file
        if tool_def and tool_def.get("name") == "write_file":
            return True
        return tool_def and tool_def.get("generatePreview")

    def _handle_preview_display(self, tool_def: Dict[str, Any], arguments: Dict[str, Any], tool_call_id: str) -> Union[bool, Dict[str, Any]]:
        """Handle preview display and return True if approved, False if rejected"""
        try:
            preview_result = tool_def["generatePreview"](arguments)
        except Exception as e:
            LogUtils.error(f"Preview generation failed: {e}")
            return True  # Continue without preview

        if not preview_result:
            return True

        # If can't approve (e.g., safety violation), show content directly without preview header
        if not preview_result.can_approve:
            LogUtils.print(preview_result.content)
            # Return the message for AI to see
            return {
                "tool_call_id": tool_call_id,
                "content": preview_result.content,
            }

        # Display preview content with header for normal previews
        # Only show file path in header if content doesn't already include it
        file_path = arguments.get('path')
        if preview_result.content and "Path:" in preview_result.content:
            # Content already includes path, don't duplicate in header
            formatted_preview = ToolFormatter.format_preview(preview_result, None)
        else:
            formatted_preview = ToolFormatter.format_preview(preview_result, file_path)
        LogUtils.print(formatted_preview)

        return True

    

    def _get_tool_approval(self, tool_name: str) -> bool:
        """Get user approval for tool if needed"""
        if not self.tool_manager.needs_approval(tool_name) or Config.yolo_mode():
            return True

        try:
            approval = input("Approve [Y/n]: ").strip().lower()
            if approval in ["n", "no"]:
                LogUtils.error("[x] Tool execution cancelled.")
                print()  # Blank line before context bar
                return False
            return True
        except (EOFError, KeyboardInterrupt):
            LogUtils.error("[x] Tool execution cancelled.")
            print()  # Blank line before context bar
            return False

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any], tool_call_id: str) -> Dict[str, Any]:
        """Execute the tool and return result"""
        try:
            exec_args = ToolExecutionArgs(name=tool_name, arguments=arguments)
            result = self.tool_manager.execute_tool_with_args(exec_args)

            # Display result using tool's own formatting
            tool_def = self.tool_manager.tools.get(tool_name)
            self.display_tool_result(result, tool_def)

            # Return result for message history (AI always gets detailed version)
            return {
                "tool_call_id": tool_call_id,
                "content": result.detailed,  # AI always receives detailed version
            }
        except Exception as e:
            LogUtils.error(f"✗ Error executing {tool_name}: {str(e)}")
            return {
                "tool_call_id": tool_call_id,
                "content": f"Error: {str(e)}",
            }

    def display_tool_result(self, result, tool_def: Dict[str, Any]) -> None:
        """Display tool execution result using the new ToolResult format"""
        if tool_def and tool_def.get("hide_results"):
            LogUtils.success("[*] Done")
        else:
            # Display based on detail mode
            if Config.detail_mode():
                # Detail mode: show detailed first, then friendly
                LogUtils.print(result.detailed)
                LogUtils.print(result.friendly)
            else:
                # Non-detail mode: show only friendly
                LogUtils.print(result.friendly)