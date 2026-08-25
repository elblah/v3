"""
Python Runtime Plugin - Advanced AI Coder Internal Operations

WARNING: IMPORTANT: This is NOT for general Python code execution!
This plugin provides AI with direct access to AI Coder's internal runtime for advanced debugging and development tasks ONLY.

Features:
- run_inline_python tool: Execute code with full AI Coder internal access
- /python-runtime command: Enable/disable the feature
- Safety: Never auto-approved, starts disabled by default

WARNING: WHEN TO USE (Clear Intent Required):
- Debugging AI Coder internal behavior and state
- Testing and developing AI Coder plugins internally
- Analyzing AI Coder component relationships
- Emergency fixes or workarounds for AI Coder issues
- Understanding AI Coder architecture for development
- Modifying AI Coder configuration or behavior

NOT ALLOWED - WHEN NOT TO USE:
- General Python programming tasks
- Regular data processing or calculations
- File operations outside AI Coder context
- User application logic
- Any task that doesn't require AI Coder internal access

Safety:
- Feature starts DISABLED by default for security
- Each execution requires explicit user approval
- Clear warnings about internal access nature
- Only enable when explicitly needed for AI Coder development/debugging
"""

from typing import Dict, Any
from aicoder.utils.log import LogUtils, LogOptions, warn, error, info, success
from aicoder.utils.bool_utils import TRUTHY, FALSY
from aicoder.core.config import Config


def create_plugin(ctx):
    """
    Create Python Runtime plugin

    ctx.app provides access to all components:
    - ctx.app.message_history
    - ctx.app.tool_manager
    - ctx.app.streaming_client
    - ctx.app.input_handler
    - ctx.app.plugin_system
    - etc.
    """

    # Tool definition — registered/unregistered via tool_manager.tools on enable/off
    def _tool_enabled() -> bool:
        return ctx.app and ctx.app.tool_manager and "run_inline_python" in ctx.app.tool_manager.tools

    def run_inline_python(args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Python code in AI Coder's runtime context"""
        code = args.get("code", "").strip()

        if not code:
            return {
                "tool": "run_inline_python",
                "friendly": "Error: Code cannot be empty",
                "detailed": "Code cannot be empty"
            }

        if not _tool_enabled():
            return {
                "tool": "run_inline_python",
                "friendly": "Runtime Python is disabled",
                "detailed": "Runtime Python is disabled. Enable with /python-runtime on"
            }

        # Prepare execution context with full access
        execution_globals = {
            "app": ctx.app,
            "ctx": ctx,
            "print": print,
            "__name__": "__runtime__",
        }

        try:
            exec(code, execution_globals)

            output_parts = []
            for key in execution_globals:
                if key not in ("app", "ctx", "print", "__builtins__", "__name__"):
                    value = execution_globals[key]
                    output_parts.append(f"{key} = {repr(value)}")

            output = "\n".join(output_parts) if output_parts else "[code executed successfully, no output]"

            return {
                "tool": "run_inline_python",
                "friendly": "✓ Code executed successfully",
                "detailed": f"Code:\n{code}\n\nOutput:\n{output}"
            }

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            return {
                "tool": "run_inline_python",
                "friendly": f"✗ Execution failed: {e}",
                "detailed": f"Code:\n{code}\n\nError: {type(e).__name__}: {e}\n\nTraceback:\n{tb}"
            }

    def format_arguments(args: Dict[str, Any]) -> Dict[str, Any]:
        """Format for approval display"""
        code = args.get("code", "")
        lines = code.split("\n")

        enabled = _tool_enabled()
        status = "ENABLED" if enabled else "DISABLED"

        if not enabled:
            return {
                "tool": "run_inline_python",
                "content": (
                    f"Runtime Python: {status}\n\n"
                    f"WARNING: Runtime Python is DISABLED - execution blocked\n"
                    f"Enable with: /python-runtime on\n\n"
                    f"Code ({len(lines)} lines):\n{code}"
                ),
                "can_approve": False
            }

        return {
            "tool": "run_inline_python",
            "content": (
                f"Runtime Python: {status}\n\n"
                f"Available in code:\n"
                f"  app  - AICoder instance (full access to all components)\n"
                f"  ctx  - PluginContext instance\n"
                f"  print - print function\n\n"
                f"Code to execute ({len(lines)} lines):\n{code}"
            ),
            "can_approve": True
        }

    def generate_preview(args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate preview"""
        code = args.get("code", "")
        lines = code.split("\n")

        enabled = _tool_enabled()
        status = "ENABLED" if enabled else "DISABLED"
        status_color = Config.colors['green'] if enabled else Config.colors['red']

        if not enabled:
            return {
                "tool": "run_inline_python",
                "content": (
                    f"Runtime Python: {status}\n\n"
                    f"WARNING: Runtime Python is DISABLED - execution blocked\n"
                    f"Enable with: /python-runtime on\n\n"
                    f"Code ({len(lines)} lines):\n{code}"
                ),
                "can_approve": False
            }

        # Show full code when enabled (no truncation)
        return {
            "tool": "run_inline_python",
            "content": (
                f"Runtime Python: {status}\n\n"
                f"Available in code:\n"
                f"  app  - AICoder instance (full access to all components)\n"
                f"  ctx  - PluginContext instance\n"
                f"  print - print function\n\n"
                f"Code to execute ({len(lines)} lines):\n{code}"
            ),
            "can_approve": True
        }

    # Build tool definition once, register/unregister via tool_manager.tools on command
    _tool_name = "run_inline_python"
    _tool_def = {
        "execute": run_inline_python,
        "description": "WARNING: INTERNAL DEBUGGING ONLY - Execute Python code with full AI Coder internal access (requires /python-runtime on). NOT for general programming!",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "WARNING: AI Coder INTERNAL code ONLY - for debugging/development (has access to 'app' = AICoder instance, 'ctx' = PluginContext, 'print')"
                }
            },
            "required": ["code"]
        },
        "auto_approved": False,
        "formatArguments": format_arguments,
        "generatePreview": generate_preview,
    }

    def _register_tool():
        if ctx.app and ctx.app.tool_manager and _tool_name not in ctx.app.tool_manager.tools:
            ctx.app.tool_manager.tools[_tool_name] = _tool_def

    def _unregister_tool():
        if ctx.app and ctx.app.tool_manager and _tool_name in ctx.app.tool_manager.tools:
            del ctx.app.tool_manager.tools[_tool_name]

    # ==================== Commands ====================

    def handle_python_runtime_command(args_str: str) -> str:
        """Handle /python-runtime command"""
        args_str = args_str.strip()

        if not args_str:
            help_text = """Python Runtime Plugin

Execute Python code inline in AI Coder's process with full access to internal state.

Commands:
    /python-runtime on     - Enable Runtime Python (AI can use run_inline_python tool)
    /python-runtime off    - Disable Runtime Python
    /python-runtime status - Show current status

Tool:
    run_inline_python - Execute Python code with full access to AI Coder context

Available in code:
    app  - AICoder instance (access all components: message_history, tool_manager, etc.)
    ctx  - PluginContext instance
    print - print function

WARNING: When enabled, AI can modify AI Coder's behavior, corrupt sessions,
   remove guards, or break the instance. Each execution requires approval.

Examples:
    /python-runtime on
    /python-runtime status
"""
            return help_text

        if args_str in TRUTHY:
            _register_tool()
            warn("Runtime Python ENABLED")
            info("AI can now use run_inline_python tool (each execution requires approval)")
            return ""
        elif args_str in FALSY:
            _unregister_tool()
            error("Runtime Python DISABLED")
            return ""
        elif args_str == "status":
            enabled = _tool_enabled()
            status = "ENABLED" if enabled else "DISABLED"
            if enabled:
                success(f"Runtime Python: {status}")
            else:
                info(f"Runtime Python: {status}")
            return ""
        else:
            return f"Unknown subcommand: {args_str}\nUsage: /python_runtime [on|off|status]"

    # Register the command (tool is NOT registered at startup — only on /python-runtime on)
    ctx.register_command("python-runtime", handle_python_runtime_command, "Control Runtime Python feature")

    # Print what was registered
    if Config.debug():
        LogUtils.print("  - run_inline_python tool")
        LogUtils.print("  - /python-runtime command")

    # No cleanup needed
    return None
