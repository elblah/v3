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
from aicoder.core.plugin_system import plugin_system as global_plugin_system
from aicoder.core.compaction_service import CompactionService
from aicoder.core.council_service import CouncilService
from aicoder.core.command_handler import CommandHandler
from aicoder.core.tool_executor import ToolExecutor
from aicoder.core.stream_processor import StreamProcessor
from aicoder.utils.log import LogUtils, LogOptions
from aicoder.type_defs.message_types import AssistantMessage
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
        self.tool_executor = ToolExecutor(self.tool_manager, self.message_history)
        self.stream_processor = StreamProcessor(self.streaming_client)
        self.input_handler = InputHandler(
            self.context_bar, self.stats, self.message_history
        )
        self.compaction_service = CompactionService(None)
        self.council_service = CouncilService()

        # Command system
        self.command_handler = CommandHandler(
            message_history=self.message_history,
            input_handler=self.input_handler,
            stats=self.stats,
        )

        # Hooks
        self.notify_hooks = None

    def initialize(self) -> None:
        """Initialize AI Coder components"""
        Config.validate_config()
        self.initialize_plugins()
        self.initialize_system_prompt()

        # Set up streaming client with message history (TS calls setApiClient on messageHistory)
        self.message_history.set_api_client(self.streaming_client)

    def initialize_system_prompt(self) -> None:
        """Initialize with system prompt focused on internal tools"""
        system_prompt = self._build_system_prompt()
        self.message_history.add_system_message(system_prompt)

    def _build_system_prompt(self) -> str:
        """Build system prompt using universal prompt builder"""
        from aicoder.core.prompt_builder import PromptBuilder

        # Initialize prompt builder if needed
        if not PromptBuilder.is_initialized():
            PromptBuilder.initialize()

        # Get tool information
        tools = self.tool_manager.get_tool_definitions()

        # Create prompt builder instance
        prompt_builder = PromptBuilder()

        # Build system prompt
        system_prompt = prompt_builder.build_system_prompt(tools)
        return system_prompt

    def run(self) -> None:
        """Run the interactive AI Coder session"""
        if Config.debug():
            LogUtils.debug(f"*** run() called, sys.stdin.isatty()={sys.stdin.isatty()}")

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
                self.process_with_ai()

            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            except Exception as e:
                LogUtils.error(f"Error: {e}")

        # Print final stats
        self.stats.print_stats()

        # Close
        self.input_handler.close()

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
                self.process_with_ai()
        except Exception as e:
            LogUtils.error(f"Error: {e}")

    def add_user_input(self, user_input: str) -> None:
        """Add user input to conversation"""
        user_input = user_input.strip()
        self.message_history.add_user_message(user_input)
        self.stats.increment_user_interactions()

        # Save to prompt history (like TypeScript version)
        from aicoder.core import prompt_history

        prompt_history.save_prompt(user_input)

    def process_with_ai(self) -> None:
        """Process conversation with AI"""
        if Config.debug():
            LogUtils.debug("*** process_with_ai called")

        self.is_processing = True

        try:
            preparation = self.prepare_for_processing()
            if Config.debug():
                LogUtils.debug(
                    f"*** prepare_for_processing returned should_continue={preparation.get('should_continue')}"
                )
            if not preparation["should_continue"]:
                return

            self.streaming_client.reset_colorizer()

            streaming_result = self.stream_response(preparation["messages"])
            if not streaming_result["should_continue"]:
                return

            has_tool_calls = self.validate_and_process_tool_calls(
                streaming_result["full_response"],
                streaming_result["accumulated_tool_calls"],
            )

            self.handle_post_processing(has_tool_calls)

        except Exception as e:
            self.handle_processing_error(e)
        finally:
            self.is_processing = False

    def prepare_for_processing(self) -> Dict[str, Any]:
        """Prepare for AI processing"""
        # Handle compaction
        if Config.auto_compact_enabled():
            current_size = self.stats.current_prompt_size or 0
            if current_size > Config.context_size():
                self.force_compaction()

        # Show context bar before AI response
        print()
        self.context_bar.print_context_bar(self.stats, self.message_history)
        LogUtils.print("AI: ", LogOptions(color=Config.colors["cyan"], bold=True))

        # Check if interrupted
        if not self.is_processing:
            print("\n[AI response interrupted before starting]")
            return {"should_continue": False, "messages": []}

        messages = self.message_history.get_messages()
        return {"should_continue": True, "messages": messages}

    def stream_response(self, messages: list) -> Dict[str, Any]:
        """Stream response from API"""
        if Config.debug():
            LogUtils.debug(f"*** stream_response called with {len(messages)} messages")

        # Use StreamProcessor to handle the streaming
        result = self.stream_processor.process_stream(
            messages,
            lambda: self.is_processing,  # is_processing_callback
            self.stream_processor.accumulate_tool_call  # process_chunk_callback
        )

        # Handle error case by adding to message history
        if result.get("error"):
            self.message_history.add_assistant_message(
                AssistantMessage(content=f"[API Error: {result['error']}]")
            )

        return result

    def validate_and_process_tool_calls(
        self, full_response: str, accumulated_tool_calls: dict
    ) -> bool:
        """Validate and process accumulated tool calls"""
        if not accumulated_tool_calls:
            self.handle_empty_response(full_response)
            return False

        valid_tool_calls = self.validate_tool_calls(accumulated_tool_calls)
        if not valid_tool_calls:
            LogUtils.error("No valid tool calls to execute")
            return False

        # Add assistant message with tool calls
        from aicoder.type_defs.message_types import AssistantMessage, MessageToolCall

        tool_calls_for_message = []
        for i, call in enumerate(valid_tool_calls):
            tool_calls_for_message.append(
                MessageToolCall(
                    id=call.get("id"),
                    type=call.get("type", "function"),
                    function={
                        "name": call.get("function", {}).get("name"),
                        "arguments": call.get("function", {}).get("arguments"),
                    },
                    index=i,
                )
            )

        self.message_history.add_assistant_message(
            AssistantMessage(
                content=full_response or "I'll help you with that.",
                tool_calls=tool_calls_for_message,
            )
        )

        self.tool_executor.execute_tool_calls(valid_tool_calls)
        return True

    def handle_post_processing(self, has_tool_calls: bool) -> None:
        """Handle post-processing after AI response"""
        if has_tool_calls and self.is_processing:
            # Just continue the main processing loop - same as TS processWithAI()
            self.process_with_ai()

    def handle_processing_error(self, error: Exception) -> None:
        """Handle processing errors"""
        LogUtils.error(f"Processing error: {error}")

    

    

    

    def initialize_plugins(self) -> None:
        """Initialize plugin system"""
        try:
            global_plugin_system.initialize()
            global_plugin_system.register_tools(self.tool_manager)
            LogUtils.success(f"[*] Loaded {len(global_plugin_system.plugins)} plugins")
        except Exception as e:
            if Config.debug():
                LogUtils.warn(f"[!] Plugin initialization failed: {e}")

    def perform_auto_compaction(self) -> None:
        """Perform automatic compaction"""
        try:
            if self.compaction_service:
                self.compaction_service.compact_messages(self.message_history)
        except Exception as e:
            if Config.debug():
                LogUtils.warn(f"[!] Auto-compaction failed: {e}")

    def force_compaction(self) -> None:
        """Force compaction of messages"""
        try:
            if self.compaction_service:
                self.compaction_service.force_compact(self.message_history)
        except Exception as e:
            LogUtils.error(f"Force compaction failed: {e}")

    def handle_empty_response(self, full_response: str) -> None:
        """Handle empty response from AI"""
        if full_response and full_response.strip() != "":
            # AI provided text response but no tools
            from aicoder.type_defs.message_types import AssistantMessage

            self.message_history.add_assistant_message(
                AssistantMessage(content=full_response)
            )
            print("")
        else:
            # AI provided no text response (this is normal when AI has nothing to say)
            # Add a minimal message to show AI responded, then continue
            from aicoder.type_defs.message_types import AssistantMessage

            self.message_history.add_assistant_message(AssistantMessage(content=""))
            print("")

    def validate_tool_calls(self, tool_calls: dict) -> list:
        """Validate tool calls"""
        return [
            tool_call
            for tool_call in tool_calls.values()
            if tool_call.get("function", {}).get("name") and tool_call.get("id")
        ]

    def call_notify_hook(self, hook_name: str) -> None:
        """Call notification hook"""
        if self.notify_hooks and hook_name in self.notify_hooks:
            try:
                self.notify_hooks[hook_name]()
            except Exception as e:
                if Config.debug():
                    LogUtils.warn(f"[!] Hook {hook_name} failed: {e}")
