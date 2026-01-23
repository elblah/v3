"""
AI Coder - Main Application Class
Clean version with clear structure
"""

import sys
import time
import os
import json
import atexit
from typing import Dict, Any

from aicoder.core.config import Config
from aicoder.core.stats import Stats
from aicoder.core.message_history import MessageHistory
from aicoder.core.tool_manager import ToolManager
from aicoder.core.streaming_client import StreamingClient
from aicoder.core.input_handler import InputHandler
from aicoder.core.context_bar import ContextBar
from aicoder.core.compaction_service import CompactionService
from aicoder.core.command_handler import CommandHandler
from aicoder.core.tool_executor import ToolExecutor
from aicoder.core.stream_processor import StreamProcessor
from aicoder.core.session_manager import SessionManager
from aicoder.core.prompt_builder import PromptBuilder
from aicoder.core.socket_server import SocketServer
from aicoder.core.plugin_system import PluginSystem
from aicoder.utils.log import LogUtils, LogOptions
from aicoder.utils.stdin_utils import read_stdin_as_string


class AICoder:
    """Main AI Coder application class"""

    def __init__(self):
        # State
        self.is_running = True
        self.is_processing = False
        self.next_prompt = None

        # Core components
        self.stats = Stats()
        self.message_history = MessageHistory(self.stats)
        self.tool_manager = ToolManager(self.stats)
        self.streaming_client = StreamingClient(self.stats, self.tool_manager)
        self.context_bar = ContextBar()
        self.input_handler = InputHandler(
            self.context_bar, self.stats, self.message_history
        )
        self.compaction_service = CompactionService(None)

        # Plugin system (ultra-fast)
        self.plugin_system = PluginSystem(plugins_dir=".aicoder/plugins")

        # Extracted components (need to be initialized after core services)
        self.tool_executor = ToolExecutor(self.tool_manager, self.message_history, self.plugin_system)
        self.stream_processor = StreamProcessor(self.streaming_client)
        self.session_manager = SessionManager(self)

        # Command system
        self.command_handler = CommandHandler(
            message_history=self.message_history,
            input_handler=self.input_handler,
            stats=self.stats,
            plugin_system=self.plugin_system,
        )

        # Socket server for external control
        self.socket_server = SocketServer(self)

        # Hooks
        self.notify_hooks = None

        # Detect pipe mode
        self._is_pipe_mode = not sys.stdin.isatty()
        
        # Auto-save functionality
        self._auto_save_enabled = os.environ.get("AICODER_AUTO_SAVE", "1").lower() in ("1", "true", "yes")
        default_path = os.path.join(".aicoder", "last-session.json")
        self._session_file_path = os.environ.get("AICODER_AUTO_SAVE_FILE", default_path)
        self._using_default_save_path = self._session_file_path == default_path

    def set_next_prompt(self, prompt: str) -> None:
        """Set next prompt to execute (for auto-council)"""
        self.next_prompt = prompt

    def get_next_prompt(self) -> str:
        """Get and clear next prompt"""
        prompt = self.next_prompt
        self.next_prompt = None
        return prompt

    def has_next_prompt(self) -> bool:
        """Check if next prompt is set"""
        return self.next_prompt is not None

    def initialize(self) -> None:
        """Initialize AI Coder components"""
        Config.validate_config()
        self.initialize_system_prompt()

        # Set up streaming client with message history (TS calls setApiClient on messageHistory)
        self.message_history.set_api_client(self.streaming_client)

        # Load plugins (ultra-fast: only if .aicoder/plugins/ exists)
        # Set app reference so plugins can access components directly via ctx.app
        self.plugin_system.set_app(self)
        self.tool_manager.set_plugin_system(self.plugin_system)
        self.message_history.set_plugin_system(self.plugin_system)

        self.plugin_system.load_plugins()

        # Register plugin tools
        plugin_tools = self.plugin_system.get_plugin_tools()
        for tool_name, tool_data in plugin_tools.items():
            tool_def = {
                "type": "plugin",
                "description": tool_data["description"],
                "parameters": tool_data["parameters"],
                "auto_approved": tool_data.get("auto_approved", False),
                "execute": tool_data["fn"],  # Store plugin function
            }
            # Add formatArguments if provided
            if tool_data.get("formatArguments"):
                tool_def["formatArguments"] = tool_data["formatArguments"]
            # Add generatePreview if provided
            if tool_data.get("generatePreview"):
                tool_def["generatePreview"] = tool_data["generatePreview"]
            self.tool_manager.tools[tool_name] = tool_def

        # Register plugin commands
        plugin_commands = self.plugin_system.get_plugin_commands()
        for cmd_name, cmd_data in plugin_commands.items():
            self.command_handler.registry.register_simple_command(
                cmd_name, cmd_data["fn"], cmd_data.get("description")
            )

        # Calculate tool tokens once at startup (after all plugins loaded)
        self._calculate_tool_tokens()

        # Update stats to include tool tokens (estimate_context adds _tools_tokens)
        self.message_history.estimate_context()

        # Start socket server for external control
        self.socket_server.start()

        # Register auto-save if enabled
        self.register_auto_save()
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

    def _calculate_tool_tokens(self) -> None:
        """Calculate tool definition tokens once at startup"""
        from aicoder.core.token_estimator import set_tool_tokens, _estimate_weighted_tokens

        tools = self.tool_manager.get_tool_definitions()
        if tools:
            tools_json = json.dumps(tools, separators=(',', ':'))
            tokens = _estimate_weighted_tokens(tools_json)
            set_tool_tokens(tokens)
            if Config.debug():
                LogUtils.debug(f"Tool tokens estimated: {tokens}")

    def initialize_system_prompt(self) -> None:
        """Initialize with system prompt focused on internal tools"""
        # Initialize prompt builder if needed
        if not PromptBuilder.is_initialized():
            PromptBuilder.initialize()

        # Build and add system prompt
        system_prompt = PromptBuilder.build_system_prompt()
        self.message_history.add_system_message(system_prompt)

    def run(self) -> None:
        """Run the interactive AI Coder session"""
        if Config.debug():
            LogUtils.debug(f"*** run() called, sys.stdin.isatty()={sys.stdin.isatty()}")

        # Check if socket-only mode
        if Config.socket_only():
            self.run_socket_only()
            return

        # Check if non-interactive
        if not sys.stdin.isatty():
            self.run_non_interactive()
            return

        # Interactive mode
        Config.print_startup_info()
        LogUtils.success("Type your message or /help for commands.")

        while self.is_running:
            try:
                # Auto-compaction check
                if self.message_history.should_auto_compact():
                    self.perform_auto_compaction()

                # Get user input
                self.call_notify_hook("on_before_user_prompt")
                self.plugin_system.call_hooks("before_user_prompt")

                # Use next_prompt if set (auto-council trigger)
                user_input = self.get_next_prompt() if self.has_next_prompt() else self.input_handler.get_user_input()

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    result = self.command_handler.handle_command(user_input)
                    if result.should_quit:
                        self.is_running = False
                        break
                    if not result.run_api_call:
                        # Check if command wants to execute another command
                        if result.command_to_execute:
                            # Set as next prompt to be processed
                            self.set_next_prompt(result.command_to_execute)
                            continue
                        continue
                    if result.message:
                        self.add_user_input(result.message)
                else:
                    self.add_user_input(user_input)

                # Process with AI
                self.session_manager.process_with_ai()

            except KeyboardInterrupt:
                continue
            except EOFError:
                continue
            except Exception as e:
                LogUtils.error(f"Error: {e}")

        # Shutdown
        self.shutdown()

    def run_non_interactive(self) -> None:
        """Run in non-interactive mode (piped input)"""
        if Config.debug():
            LogUtils.debug("*** run_non_interactive called")

        try:
            user_input = read_stdin_as_string()
            if Config.debug():
                LogUtils.debug(f"*** got stdin input: {repr(user_input[:50])}")
            if not user_input:
                if Config.debug():
                    LogUtils.debug("*** no stdin input, returning")
                return

            # Get message count before processing to detect if commands added messages
            initial_message_count = len(self.message_history.get_messages())

            # Process each line for commands
            lines = user_input.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Handle commands
                if line.startswith("/"):
                    result = self.command_handler.handle_command(line)
                    if result.should_quit:
                        # Command requested exit (e.g., /help, /quit)
                        # Don't process further, exit now
                        self.shutdown()
                        return
                    if not result.run_api_call:
                        # Command executed locally (e.g., /help) or added its own message
                        # (/council, /ralph) - skip adding message but continue
                        continue
                    if result.message:
                        self.add_user_input(result.message)
                else:
                    self.add_user_input(line)

            # Check if there are messages to process:
            # - Direct user messages added
            # - Commands that added their own messages (like /council)
            # - Commands that set next_prompt (like /ralph)
            # But NOT initial system messages that were already there
            current_message_count = len(self.message_history.get_messages())
            has_new_messages = current_message_count > initial_message_count
            has_next_prompt = self.has_next_prompt()

            # Process with AI only if new messages were added OR next_prompt is set
            if has_new_messages or has_next_prompt:
                # If next_prompt is set, get it and add to history (like interactive mode does)
                if has_next_prompt:
                    next_prompt = self.get_next_prompt()
                    if next_prompt:
                        self.add_user_input(next_prompt)
                
                self.session_manager.process_with_ai()
        except Exception as e:
            LogUtils.error(f"Error: {e}")

        # Shutdown
        self.shutdown()

    def run_socket_only(self) -> None:
        """Run in socket-only mode (no readline, only socket commands)"""
        if Config.debug():
            LogUtils.debug("*** run_socket_only called")

        # Auto-enable YOLO mode since approval system won't work without readline
        Config.set_yolo_mode(True)
        LogUtils.success("YOLO mode auto-enabled (socket-only mode)")

        Config.print_startup_info()
        LogUtils.success("Socket-only mode. Use socket commands to control AI Coder.")

        # Keep socket server alive, but don't read from stdin
        while self.is_running:
            try:
                # Sleep to keep socket server alive in background thread
                time.sleep(1)
            except KeyboardInterrupt:
                break
            except Exception as e:
                LogUtils.error(f"Error: {e}")

        # Shutdown
        self.shutdown()

    def add_user_input(self, user_input: str) -> None:
        """Add user input to conversation"""
        # Apply plugin transformations (snippets, etc.)
        transformed_input = self.plugin_system.call_hooks_with_return(
            "after_user_prompt", user_input
        )

        # Use transformed input (or original if hook returned None)
        final_input = transformed_input if transformed_input is not None else user_input

        final_input = final_input.strip()
        self.message_history.add_user_message(final_input)
        self.stats.increment_user_interactions()

        # Save to prompt history ()
        from aicoder.core import prompt_history

        prompt_history.save_prompt(final_input)

    def add_plugin_message(self, message: str) -> None:
        """Add a message from plugins to conversation"""
        self.message_history.add_user_message(message)
        self.stats.increment_user_interactions()

    def handle_test_message(self, message: Dict[str, Any]) -> list:
        """
        Handle test message injection for testing purposes.
        
        This method bypasses SSE stream processing and directly processes
        assistant messages with tool calls using the same pipeline as normal operation.
        
        Args:
            message: Dictionary containing assistant message with optional tool_calls
            
        Returns:
            List of tool execution results
        """
        # Use dict for message
                
        assistant_message = {
            "content": message.get("content", ""),
            "tool_calls": message.get("tool_calls", [])
        }
        
        # Add the message to history using proper method
        self.message_history.add_assistant_message(assistant_message)
        
        # Execute tool calls if present
        if "tool_calls" in message and message["tool_calls"]:
            # Create placeholder results for testing
            results = []
            for tool_call in message["tool_calls"]:
                results.append({
                    "tool_call_id": tool_call.get("id", ""),
                    "success": True,
                    "content": "Tool executed via test injection"
                })
            return results
        
        return []

    def perform_auto_compaction(self) -> None:
        """Perform auto-compaction (delegates to session_manager)"""
        self.session_manager._perform_auto_compaction()

    def call_notify_hook(self, hook_name: str) -> None:
        """Call notification hook"""
        if self.notify_hooks and hook_name in self.notify_hooks:
            try:
                self.notify_hooks[hook_name]()
            except Exception as e:
                if Config.debug():
                    LogUtils.warn(f"[!] Hook {hook_name} failed: {e}")

    def save_session(self, force: bool = False) -> bool:
        """
        Centralized method to save the current session.
        
        Args:
            force: If True, saves even in pipe mode with default path
            
        Returns:
            bool: True if save was attempted/successful, False if skipped due to pipe mode rules
        """
        # In pipe mode, only save if forced or if a custom file path was explicitly set
        if self._is_pipe_mode and self._using_default_save_path and not force:
            return False
        
        try:
            self.command_handler.handle_command(f"/save {self._session_file_path}")
            return True
        except Exception:
            # Don't let exceptions propagate during shutdown
            return False

    def shutdown(self) -> None:
        """Clean shutdown"""
        self.socket_server.stop()
        self.input_handler.close()

    def register_auto_save(self) -> None:
        """Register auto-save with Python's atexit mechanism"""
        if self._auto_save_enabled:
            atexit.register(self._auto_save_on_exit)

    def _auto_save_on_exit(self) -> None:
        """Auto-save callback with pipe mode protection"""
        self.save_session()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown (SIGTERM only, SIGINT preserved for Ctrl+C)"""
        import signal
        
        def handle_signal(signum, frame):
            LogUtils.print(f"\nReceived signal {signum}, shutting down gracefully...")
            # Force save on signal-induced shutdown (user explicitly wants to exit)
            if self._auto_save_enabled:
                self.save_session(force=True)
            self.shutdown()
            sys.exit(0)
        
        # Only handle SIGTERM, leave SIGINT (Ctrl+C) to be handled by the main loop's KeyboardInterrupt
        signal.signal(signal.SIGTERM, handle_signal)
        # SIGINT is left to default behavior, will raise KeyboardInterrupt in main loop
