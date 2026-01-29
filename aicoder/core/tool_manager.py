"""
Tool manager for AI Coder - Internal tools only

"""

import json
from typing import Dict, Any, Optional, List, Set

from aicoder.core.config import Config
from aicoder.core.stats import Stats
from aicoder.core.tool_formatter import ToolFormatter
from aicoder.tools.internal.read_file import TOOL_DEFINITION as READ_FILE_DEF
from aicoder.tools.internal.write_file import TOOL_DEFINITION as WRITE_FILE_DEF
from aicoder.tools.internal.edit_file import TOOL_DEFINITION as EDIT_FILE_DEF
from aicoder.tools.internal.run_shell_command import (
    TOOL_DEFINITION as RUN_SHELL_COMMAND_DEF,
)
from aicoder.tools.internal.grep import TOOL_DEFINITION as GREP_DEF
from aicoder.tools.internal.list_directory import TOOL_DEFINITION as LIST_DIRECTORY_DEF


class ToolManager:
    """Tool manager"""

    def __init__(self, stats: Stats):
        self.stats = stats
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.read_files: Set[str] = set()
        self.plugin_system = None  # Will be set by aicoder

        # Register internal tools
        self._register_internal_tools()

    def set_plugin_system(self, plugin_system) -> None:
        """Set plugin system reference and initialize tools that need it"""
        self.plugin_system = plugin_system

        # Initialize internal tools that need plugin system access
        from aicoder.tools.internal.write_file import set_plugin_system as write_file_set_plugin_system
        write_file_set_plugin_system(plugin_system)

        from aicoder.tools.internal.edit_file import set_plugin_system as edit_file_set_plugin_system
        edit_file_set_plugin_system(plugin_system)

    def _register_internal_tools(self):
        """Register all internal tools (filtered by TOOLS_ALLOW if set)"""
        all_tools = {
            "read_file": READ_FILE_DEF,
            "write_file": WRITE_FILE_DEF,
            "edit_file": EDIT_FILE_DEF,
            "run_shell_command": RUN_SHELL_COMMAND_DEF,
            "grep": GREP_DEF,
            "list_directory": LIST_DIRECTORY_DEF,
        }

        allowed = Config.tools_allow()
        if allowed is not None:
            # Only register allowed tools
            for name, tool_def in all_tools.items():
                if name in allowed:
                    self.tools[name] = tool_def
        else:
            # Register all tools
            self.tools.update(all_tools)

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get all tool definitions for API request"""
        definitions = []

        for name, tool_def in self.tools.items():
            definition = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool_def.get("description"),
                    "parameters": tool_def.get("parameters"),
                },
            }
            definitions.append(definition)

        return definitions

    def execute_tool_call(
        self, tool_call: Dict[str, Any], skip_preview: bool = False
    ) -> Dict[str, Any]:
        """Execute a tool call (internal tools only)"""
        tool_id = tool_call.get("id")
        func = tool_call.get("function", {})
        name = func.get("name")
        args = func.get("arguments", "{}")

        try:
            tool_def = self._validate_tool(name)
            args_obj = self._parse_arguments(args)

            # Validate required arguments for each tool
            self._validate_tool_arguments(name, args_obj)

            # Execute the appropriate tool
            tool_output = self._execute_tool(name, args_obj, tool_def)

            return self._format_result(tool_output, tool_def, name, tool_id)

        except Exception as error:
            return {
                "tool": name,
                "friendly": f"✗ Error executing {name}: {str(error)}",
                "detailed": f"Tool execution failed: {str(error)}",
                "success": False,
            }

    def _validate_tool(self, name: Optional[str]) -> Dict[str, Any]:
        """Validate tool exists"""
        if not name:
            raise Exception("Tool name is required")

        tool_def = self.tools.get(name)
        if not tool_def:
            raise Exception(f"Unknown tool: {name}")

        return tool_def

    def _parse_arguments(self, args: str) -> Dict[str, Any]:
        """Parse tool arguments from JSON string"""
        try:
            return json.loads(args)
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON in tool arguments: {e}")

    def _validate_tool_arguments(self, name: str, args_obj: Dict[str, Any]) -> None:
        """Validate required arguments for each tool"""
        # Validation handled by individual tools in execute
        pass

    def _execute_tool(
        self, name: str, args_obj: Dict[str, Any], tool_def: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the tool"""
        try:
            execute_func = tool_def.get("execute")
            if not execute_func:
                raise Exception(f"Tool {name} has no execute method")

            tool_output = execute_func(args_obj)

            # Track that we read this file (special case for read_file)
            if name == "read_file" and "path" in args_obj:
                self.read_files.add(args_obj["path"])

            return tool_output

        except Exception as exec_error:
            raise Exception(f"Tool execution failed for {name}: {str(exec_error)}")

    def _format_result(
        self,
        tool_output: Dict[str, Any],
        tool_def: Dict[str, Any],
        tool_name: str,
        tool_call_id: str,
    ) -> Dict[str, Any]:
        """Format result for AI and display"""
        # Format for AI and display
        ai_result = ToolFormatter.format_for_ai(tool_output)
        friendly_result = ToolFormatter.format_for_display(tool_output)

        # Check if result is too large
        ai_result = self._check_size(ai_result, tool_def, tool_name)

        return {
            "tool": tool_name,
            "friendly": friendly_result,
            "detailed": ai_result,
            "success": True,
        }

    def _check_size(
        self, content: str, tool_def: Dict[str, Any], tool_name: str
    ) -> str:
        """Check if content is too large and truncate if needed"""
        max_size = Config.max_tool_result_size()
        max_len = max_size - (max_size // 100)  # Leave 1% room for error message

        if len(content) > max_len:
            warning = f"\n\nWARNING: Content for {tool_name} is too large ({len(content)} bytes). Truncating to {max_len} bytes."
            return content[:max_len] + warning

        return content

    def needs_approval(self, tool_name: str) -> bool:
        """Check if a tool needs approval"""
        tool_def = self.tools.get(tool_name)
        if not tool_def:
            return True
        return not tool_def.get("auto_approved", False)

    def execute_tool_with_args(self, execution_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool with ToolExecutionArgs (compatibility method)"""
        # Create ToolCall dict from execution args
        name = execution_args["name"]
        args = execution_args["arguments"]
        tool_call = {
            "id": f"tool_{name}_{hash(str(args))}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args),
            },
        }

        # Execute using existing method
        return self.execute_tool_call(tool_call)
