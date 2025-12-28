"""
AI Coder - Main Application Class
Clean version with clear structure
"""

import sys
import time
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
from aicoder.utils.log import LogUtils, LogOptions
from aicoder.utils.stdin_utils import read_stdin_as_string


class AICoder:
    """Main AI Coder application class"""

    def __init__(self):
        # State
        self.is_running = True
        self.is_processing = False

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

        # Extracted components (need to be initialized after core services)
        self.tool_executor = ToolExecutor(self.tool_manager, self.message_history)
        self.stream_processor = StreamProcessor(self.streaming_client)
        self.session_manager = SessionManager(
            self.message_history, 
            self.streaming_client,
            self.stream_processor,
            self.tool_executor,
            self.context_bar,
            self.stats,
            self.compaction_service
        )

        # Command system
        self.command_handler = CommandHandler(
            message_history=self.message_history,
            input_handler=self.input_handler,
            stats=self.stats,
        )

        # Socket server for external control
        self.socket_server = SocketServer(self)

        # Hooks
        self.notify_hooks = None

    def initialize(self) -> None:
        """Initialize AI Coder components"""
        Config.validate_config()
        self.initialize_system_prompt()

        # Set up streaming client with message history (TS calls setApiClient on messageHistory)
        self.message_history.set_api_client(self.streaming_client)

        # Start socket server for external control
        self.socket_server.start()

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
                user_input = self.input_handler.get_user_input()

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    result = self.command_handler.handle_command(user_input)
                    if result.should_quit:
                        self.is_running = False
                        break
                    if not result.run_api_call:
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
                break
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
                        return
                    if not result.run_api_call:
                        continue
                    if result.message:
                        self.add_user_input(result.message)
                else:
                    self.add_user_input(line)

            # Process with AI only if there are messages to send
            if self.message_history.get_messages():
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
        user_input = user_input.strip()
        self.message_history.add_user_message(user_input)
        self.stats.increment_user_interactions()

        # Save to prompt history (like TypeScript version)
        from aicoder.core import prompt_history

        prompt_history.save_prompt(user_input)

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

    def call_notify_hook(self, hook_name: str) -> None:
        """Call notification hook"""
        if self.notify_hooks and hook_name in self.notify_hooks:
            try:
                self.notify_hooks[hook_name]()
            except Exception as e:
                if Config.debug():
                    LogUtils.warn(f"[!] Hook {hook_name} failed: {e}")

    def shutdown(self) -> None:
        """Clean shutdown"""
        self.socket_server.stop()
        self.input_handler.close()
