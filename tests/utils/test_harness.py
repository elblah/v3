#!/usr/bin/env python3

"""
Test harness orchestrator for comprehensive AI Coder testing.

This class combines PrintCapture and MessageInjector to provide a complete
testing infrastructure for AI Coder scenarios, including multi-turn conversations
and exact output verification.
"""

import os
import tempfile
from typing import List, Dict, Any, Optional, ContextManager
from contextlib import contextmanager

from .print_capture import PrintCapture, ANSICodes
from .message_injector import MessageInjector, ToolCall
from aicoder.core.aicoder import AICoder


class TestHarness:
    """
    Complete test harness for AI Coder testing.
    
    Provides:
    - Print output capture with ANSI codes
    - Message injection capabilities  
    - Test file management
    - Output verification helpers
    - Reset capabilities between tests
    """
    
    def __init__(self, temp_dir: Optional[str] = None):
        """
        Initialize test harness.
        
        Args:
            temp_dir: Optional temporary directory for test files
        """
        self.temp_dir = temp_dir or tempfile.mkdtemp(prefix="aicoder_test_")
        self.print_capture = PrintCapture()
        self.aicoder: Optional[AICoder] = None
        self.message_injector: Optional[MessageInjector] = None
        self.input_responses = []  # Queue of responses for input() calls
        self.original_input = None
        
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
    
    @contextmanager
    def capture_output(self) -> ContextManager[PrintCapture]:
        """Context manager for capturing print output."""
        with self.print_capture as capture:
            yield capture
    
    def setup_aicoder(self, working_dir: Optional[str] = None) -> None:
        """
        Setup AI Coder instance for testing.
        
        Args:
            working_dir: Working directory for AI Coder (defaults to temp_dir)
        """
        if working_dir is None:
            working_dir = self.temp_dir
        
        # Store original directory and change to working directory
        self.original_cwd = os.getcwd()
        os.chdir(working_dir)
        
        # Enable YOLO mode for testing (auto-approves tools)
        os.environ['YOLO_MODE'] = '1'
        
        # Import and initialize AI Coder
        from aicoder.core.aicoder import AICoder
        self.aicoder = AICoder()

        # Setup message injector
        self.message_injector = MessageInjector(self.aicoder)
        
        # Setup input monkey patching
        self._setup_input_mock()
    
    def reset_between_tests(self) -> None:
        """Reset all state between test runs."""
        # Reset print capture
        self.print_capture.reset()
        
        # Reset message injector if available
        if self.message_injector:
            self.message_injector.reset()
        
        # Clear file access tracker for clean state
        from aicoder.core.file_access_tracker import FileAccessTracker
        FileAccessTracker.clear_state()
    
    def create_test_file(self, filename: str, content: str = "test content") -> str:
        """
        Create a test file in the temp directory.
        
        Args:
            filename: Name of the file to create
            content: Content to write to the file
            
        Returns:
            Full path to created file
        """
        filepath = os.path.join(self.temp_dir, filename)
        with open(filepath, 'w') as f:
            f.write(content)
        return filepath
    
    def get_test_file_path(self, filename: str) -> str:
        """Get full path for a test file."""
        return os.path.join(self.temp_dir, filename)
    
    def inject_and_capture(self, tool_calls: List[ToolCall]) -> tuple[List[str], List[Dict[str, Any]]]:
        """
        Inject tool calls and capture all output.
        
        Args:
            tool_calls: List of tool calls to execute
            
        Returns:
            Tuple of (captured_output_lines, tool_results)
        """
        if not self.message_injector:
            raise RuntimeError("Must call setup_aicoder() first")
        
        self.reset_between_tests()
        
        with self.capture_output():
            tool_results = self.message_injector.inject_tool_calls(tool_calls)
        
        output_lines = self.print_capture.get_output()
        return output_lines, tool_results
    
    def inject_message_and_capture(self, content: str, tool_calls: Optional[List[ToolCall]] = None) -> tuple[List[str], List[Dict[str, Any]]]:
        """
        Inject assistant message and capture all output.
        
        Args:
            content: Assistant message content
            tool_calls: Optional tool calls
            
        Returns:
            Tuple of (captured_output_lines, tool_results)
        """
        if not self.message_injector:
            raise RuntimeError("Must call setup_aicoder() first")
        
        self.reset_between_tests()
        
        from .message_injector import AssistantMessage
        message = AssistantMessage(content=content, tool_calls=tool_calls)
        
        with self.capture_output():
            tool_results = self.message_injector.inject_assistant_message(message)
        
        output_lines = self.print_capture.get_output()
        return output_lines, tool_results
    
    def verify_warning_format(self, output_lines: List[str], tool_name: str, file_path: str) -> Dict[str, bool]:
        """
        Verify exact warning format in output.
        
        Args:
            output_lines: Captured output lines
            tool_name: Expected tool name
            file_path: Expected file path
            
        Returns:
            Dictionary with verification results
        """
        output_text = ''.join(output_lines)
        
        # Import Config to get actual colors
        from aicoder.core.config import Config
        
        # Check for exact format components
        results = {
            "has_tool_header": f"[*] Tool: {tool_name}" in output_text,
            "has_path_display": f"Path: {file_path}" in output_text,
            "has_warning": "[!] Warning: The file must be read before editing." in output_text,
            "has_yellow_color": Config.colors["yellow"] in output_text,
            "has_reset_codes": Config.colors["reset"] in output_text,
            "correct_order": True
        }
        
        # Check correct order: tool header, then preview, then path, then warning
        tool_pos = output_text.find(f"[*] Tool: {tool_name}")
        preview_pos = output_text.find("[PREVIEW]")
        path_pos = output_text.find(f"Path: {file_path}")
        warn_pos = output_text.find("[!] Warning: The file must be read before editing.")
        
        if -1 in [tool_pos, preview_pos, path_pos, warn_pos]:
            results["correct_order"] = False
        else:
            results["correct_order"] = (tool_pos < preview_pos < path_pos < warn_pos)
        
        return results
    
    def count_safety_violations(self, output_lines: List[str]) -> int:
        """Count safety violation warnings in output."""
        text = ''.join(output_lines)
        return text.count("[!] Warning: The file must be read before editing.")
    
    def get_tool_execution_results(self, tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract successful tool execution results."""
        successful = []
        for result in tool_results:
            if isinstance(result, dict) and result.get('success', True):
                successful.append(result)
        return successful
    
    def get_tool_execution_errors(self, tool_results: List[Dict[str, Any]]) -> List[str]:
        """Extract error messages from tool execution results."""
        errors = []
        for result in tool_results:
            if isinstance(result, dict):
                if 'error' in result:
                    errors.append(result['error'])
                elif not result.get('success', True):
                    errors.append(f"Tool execution failed: {result}")
        return errors
    
    def cleanup(self) -> None:
        """Clean up test harness resources."""
        import shutil
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception:
            pass  # Ignore cleanup errors
        
        self.print_capture.reset()
        self.aicoder = None
        self.message_injector = None
        
        # Restore original directory
        if hasattr(self, 'original_cwd'):
            os.chdir(self.original_cwd)
        
        # Restore original input function
        if self.original_input:
            import builtins
            builtins.input = self.original_input
            self.original_input = None
    
    def _setup_input_mock(self) -> None:
        """Setup input() monkey patching to prevent blocking."""
        import builtins
        
        self.original_input = builtins.input
        
        def mock_input(prompt: str = "") -> str:
            """Mock input that returns queued responses or defaults."""
            if self.input_responses:
                response = self.input_responses.pop(0)
                return response
            
            # Default responses for common prompts
            prompt_lower = prompt.lower()
            if "approve" in prompt_lower or "continue" in prompt_lower:
                return "y"  # Approve by default
            elif "choice" in prompt_lower:
                return "1"  # First option
            
            return ""  # Empty default
        
        builtins.input = mock_input
    
    def add_input_response(self, response: str) -> None:
        """Add a response to be returned by the next input() call."""
        self.input_responses.append(response)
    
    def clear_input_responses(self) -> None:
        """Clear all queued input responses."""
        self.input_responses.clear()
    
    @contextmanager
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()


# Utility functions for common test patterns
class TestPatterns:
    """Common test patterns for safety mechanism testing."""
    
    @staticmethod
    def safety_violation_test(harness: TestHarness, tool_name: str, file_path: str) -> Dict[str, Any]:
        """
        Test safety violation scenario for a tool.
        
        Args:
            harness: TestHarness instance
            tool_name: Name of the tool to test
            file_path: Path to test file
            
        Returns:
            Test results dictionary
        """
        # Create test file (get full path first)
        full_file_path = harness.get_test_file_path(file_path)
        harness.create_test_file(file_path, "existing content")
        
        # Create tool call for writing without reading
        from .message_injector import ToolCall
        
        if tool_name == "write_file":
            tool_call = ToolCall(
                id="test_1",
                function_name="write_file",
                arguments={"path": file_path, "content": "new content"}
            )
        elif tool_name == "edit_file":
            tool_call = ToolCall(
                id="test_1", 
                function_name="edit_file",
                arguments={
                    "path": file_path,
                    "old_string": "existing content",
                    "new_string": "new content"
                }
            )
        else:
            raise ValueError(f"Unsupported tool for safety test: {tool_name}")
        
        # Inject and capture
        output_lines, tool_results = harness.inject_and_capture([tool_call])
        
        # Verify format
        format_results = harness.verify_warning_format(output_lines, tool_name, file_path)
        
        # Count violations
        violation_count = harness.count_safety_violations(output_lines)
        
        # Get execution results
        successful_results = harness.get_tool_execution_results(tool_results)
        errors = harness.get_tool_execution_errors(tool_results)
        
        return {
            "tool_name": tool_name,
            "file_path": full_file_path,  # Full path for test verification
            "file_name": file_path,  # Just filename for format checking
            "output_lines": output_lines,
            "tool_results": tool_results,
            "format_results": format_results,
            "violation_count": violation_count,
            "successful_results": successful_results,
            "errors": errors,
            "test_passed": format_results["has_warning"] and violation_count > 0
        }