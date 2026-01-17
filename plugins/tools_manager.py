"""
Tools Manager Plugin - Manage available tools

Features:
- List all available tools (internal and plugin)
- Show disabled tools in separate section
- Show detailed information about a specific tool
- Disable tools (temporarily remove from tool definitions)
- Enable tools (restore disabled tools)
- Bulk enable/disable all tools

Commands:
- /tools                          - List all tools (same as /tools list)
- /tools list                     - List all available tools
- /tools show <tool_name>         - Show detailed information about a tool
- /tools disable <tool_name>      - Disable a tool
- /tools enable <tool_name>       - Enable a previously disabled tool
- /tools disable-all              - Disable all tools (use with caution!)
- /tools enable-all               - Enable all disabled tools
- /tools help                     - Show help message
"""

from typing import Dict, Any, Set

from aicoder.core.config import Config


def create_plugin(ctx):
    """Tools manager plugin"""

    # Internal storage for disabled tools (plugin state in closure)
    disabled_tools: Dict[str, Dict[str, Any]] = {}

    def get_all_tools() -> Dict[str, Dict[str, Any]]:
        """Get all tools from tool_manager"""
        if not ctx.app or not ctx.app.tool_manager:
            return {}
        return ctx.app.tool_manager.tools

    def list_tools() -> str:
        """List all available tools"""
        tools = get_all_tools()
        lines = []

        # Categorize tools by type
        internal_tools = []
        plugin_tools = []

        # Only show "Available Tools" section if there are tools
        if tools:
            lines.append("Available Tools:")
            lines.append("")

            for name, tool_def in tools.items():
                tool_type = tool_def.get("type", "unknown")
                description = tool_def.get("description", "No description")
                auto_approved = tool_def.get("auto_approved", False)

                # Create status indicator
                status = "[auto]" if auto_approved else "[needs approval]"

                tool_info = f"  {name:25} - {description:50} {status}"

                if tool_type == "internal":
                    internal_tools.append((name, tool_info))
                elif tool_type == "plugin":
                    plugin_tools.append((name, tool_info))
                else:
                    internal_tools.append((name, tool_info))

            # Sort and display
            internal_tools.sort()
            plugin_tools.sort()

            if internal_tools:
                lines.append("Internal Tools:")
                for _, info in internal_tools:
                    lines.append(info)
                lines.append("")

            if plugin_tools:
                lines.append("Plugin Tools:")
                for _, info in plugin_tools:
                    lines.append(info)
                lines.append("")

            lines.append(f"Total: {len(tools)} tools")



        # Add disabled tools section
        if disabled_tools:
            lines.append("")
            lines.append("Disabled Tools:")
            lines.append("")

            disabled_internal = []
            disabled_plugin = []

            for name, tool_def in disabled_tools.items():
                tool_type = tool_def.get("type", "unknown")
                description = tool_def.get("description", "No description")
                auto_approved = tool_def.get("auto_approved", False)

                status = "[auto]" if auto_approved else "[needs approval]"
                tool_info = f"  {name:25} - {description:50} {status}"

                if tool_type == "internal":
                    disabled_internal.append((name, tool_info))
                elif tool_type == "plugin":
                    disabled_plugin.append((name, tool_info))
                else:
                    disabled_internal.append((name, tool_info))

            disabled_internal.sort()
            disabled_plugin.sort()

            if disabled_internal:
                lines.append("  Internal (disabled):")
                for _, info in disabled_internal:
                    lines.append(info)

            if disabled_plugin:
                if disabled_internal:
                    lines.append("")
                lines.append("  Plugin (disabled):")
                for _, info in disabled_plugin:
                    lines.append(info)

            lines.append("")
            lines.append(f"Total disabled: {len(disabled_tools)} tools")
            lines.append("")
            lines.append("Tip: Use /tools enable <tool_name> to re-enable specific tools")
            lines.append("Tip: Use /tools enable-all to re-enable all disabled tools")

        return "\n".join(lines)

    def show_tool(tool_name: str) -> str:
        """Show detailed information about a specific tool"""
        tools = get_all_tools()
        tool_def = tools.get(tool_name)

        if not tool_def:
            # Check if it's a disabled tool
            if tool_name in disabled_tools:
                return f"Tool '{tool_name}' is currently DISABLED\n\nTo enable it, use: /tools enable {tool_name}"
            return f"Tool '{tool_name}' not found\n\nUse /tools list to see all available tools"

        lines = [f"Tool: {tool_name}", "=" * 60, ""]

        # Type
        tool_type = tool_def.get("type", "unknown")
        lines.append(f"Type: {tool_type}")
        lines.append("")

        # Description
        description = tool_def.get("description", "No description")
        lines.append(f"Description:")
        lines.append(f"  {description}")
        lines.append("")

        # Auto-approved
        auto_approved = tool_def.get("auto_approved", False)
        lines.append(f"Auto-approved: {'Yes' if auto_approved else 'No'}")
        lines.append("")

        # Parameters
        parameters = tool_def.get("parameters", {})
        if parameters:
            lines.append("Parameters:")
            props = parameters.get("properties", {})
            required = set(parameters.get("required", []))

            if props:
                for param_name, param_info in props.items():
                    param_type = param_info.get("type", "unknown")
                    param_desc = param_info.get("description", "")
                    is_required = param_name in required

                    req_marker = "*" if is_required else ""
                    lines.append(f"  {param_name}{req_marker}")
                    lines.append(f"    Type: {param_type}")

                    if param_desc:
                        lines.append(f"    Description: {param_desc}")

                    # Show default if exists
                    if "default" in param_info:
                        lines.append(f"    Default: {param_info['default']}")

                    lines.append("")
            else:
                lines.append("  No parameters")
        else:
            lines.append("Parameters: None")
        lines.append("")

        # Footer
        lines.append("Legend: * = required parameter")
        lines.append("")
        lines.append(f"To disable this tool, use: /tools disable {tool_name}")

        return "\n".join(lines)

    def disable_tool(tool_name: str) -> str:
        """Disable a tool by moving it to internal storage"""
        if not tool_name:
            return "Error: Tool name is required\nUsage: /tools disable <tool_name>"

        tools = get_all_tools()

        if tool_name not in tools:
            return f"Error: Tool '{tool_name}' not found\n\nUse /tools list to see all available tools"

        if tool_name in disabled_tools:
            return f"Error: Tool '{tool_name}' is already disabled"

        # Store the tool definition in our internal storage
        disabled_tools[tool_name] = tools[tool_name].copy()

        # Remove from tool_manager.tools
        del tools[tool_name]

        return f"Tool '{tool_name}' has been disabled\n\nTo enable it, use: /tools enable {tool_name}"

    def enable_tool(tool_name: str) -> str:
        """Enable a tool by moving it back from internal storage"""
        if not tool_name:
            return "Error: Tool name is required\nUsage: /tools enable <tool_name>"

        if tool_name not in disabled_tools:
            return f"Error: Tool '{tool_name}' is not disabled\n\nUse /tools list to see all available tools"

        # Get the tool definition from internal storage
        tool_def = disabled_tools[tool_name]

        # Restore to tool_manager.tools
        tools = get_all_tools()
        tools[tool_name] = tool_def

        # Remove from internal storage
        del disabled_tools[tool_name]

        return f"Tool '{tool_name}' has been enabled"

    def disable_all_tools() -> str:
        """Disable all tools"""
        tools = get_all_tools()

        if not tools:
            return "No tools available to disable"

        if not disabled_tools:
            # No tools are disabled yet, disable all
            count = 0
            for name, tool_def in list(tools.items()):
                disabled_tools[name] = tool_def.copy()
                del tools[name]
                count += 1

            return f"WARNING: All {count} tools have been disabled!\n\nTo re-enable them, use:\n  /tools enable-all (re-enable all)\n  /tools enable <tool_name> (re-enable specific)"

        # Some tools are already disabled, disable the rest
        remaining = list(tools.keys())
        count = 0
        for name in remaining:
            disabled_tools[name] = tools[name].copy()
            del tools[name]
            count += 1

        return f"Disabled {count} tools (in addition to {len(disabled_tools) - count} already disabled)\n\nTotal disabled: {len(disabled_tools)}\n\nTo re-enable, use: /tools enable-all"

    def enable_all_tools() -> str:
        """Enable all disabled tools"""
        if not disabled_tools:
            return "No tools are currently disabled"

        count = 0
        tools = get_all_tools()

        for name, tool_def in list(disabled_tools.items()):
            tools[name] = tool_def
            del disabled_tools[name]
            count += 1

        return f"Successfully re-enabled {count} tools\n\nTotal available tools: {len(tools)}"

    def handle_tools_command(args_str: str) -> str:
        """
        Handle /tools command

        Usage:
            /tools                           - List all tools (same as /tools list)
            /tools list                      - List all tools
            /tools show <tool_name>          - Show detailed information about a tool
            /tools disable <tool_name>       - Disable a tool
            /tools enable <tool_name>        - Enable a previously disabled tool
            /tools disable-all               - Disable all tools (use with caution!)
            /tools enable-all                - Enable all disabled tools
            /tools help                      - Show help message
        """
        if not args_str or not args_str.strip():
            # No arguments - show list
            return list_tools()

        # Parse command
        parts = args_str.strip().split(maxsplit=1)
        command = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if command == "list":
            return list_tools()

        elif command == "show":
            if not rest:
                return "Error: Tool name is required\nUsage: /tools show <tool_name>"
            return show_tool(rest.strip())

        elif command == "disable":
            if rest == "all":
                # /tools disable all
                return disable_all_tools()
            return disable_tool(rest.strip())

        elif command == "enable":
            if rest == "all":
                # /tools enable all
                return enable_all_tools()
            return enable_tool(rest.strip())

        elif command == "disable-all":
            return disable_all_tools()

        elif command == "enable-all":
            return enable_all_tools()

        elif command == "help":
            return """Tools Manager Plugin

Manage available tools (both internal and plugin tools).

Commands:
    /tools                           - List all available tools (including disabled)
    /tools list                      - List all available tools
    /tools show <tool_name>          - Show detailed information about a tool
    /tools disable <tool_name>       - Disable a tool (temporarily remove it)
    /tools enable <tool_name>        - Enable a previously disabled tool
    /tools disable-all               - Disable ALL tools (use with caution!)
    /tools enable-all                - Enable ALL disabled tools
    /tools help                      - Show this help message

Examples:
    /tools                           - Show all tools (including disabled ones)
    /tools show read_file            - Show details about read_file tool
    /tools disable web_search        - Disable web_search tool
    /tools enable web_search         - Enable web_search tool again
    /tools disable-all               - Disable all tools at once
    /tools enable-all                - Re-enable all disabled tools

Notes:
    - Disabled tools are shown in a separate "Disabled Tools" section
    - Disabled tools are stored internally and can be re-enabled at any time
    - The AI cannot use disabled tools until they are re-enabled
    - Internal tools and plugin tools are both managed the same way
    - Use disable-all / enable-all with caution
"""

        else:
            # Unknown command - maybe it's a tool name? Try showing it
            if command in get_all_tools():
                return show_tool(command)
            else:
                return f"Unknown command: {command}\n\nUse /tools help for usage information"

    # Register the /tools command
    ctx.register_command("/tools", handle_tools_command, description="Manage available tools")

    if Config.debug():
        print("  - /tools command")
