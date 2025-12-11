#!/usr/bin/env python3
"""Test edit_file with ToolExecutor to check preview formatting"""

import tempfile
import os
import json
from aicoder.core.tool_executor import ToolExecutor
from aicoder.core.tool_manager import ToolManager
from aicoder.core.message_history import MessageHistory
from aicoder.core.config import Config
from aicoder.core.file_access_tracker import FileAccessTracker

# Disable sandbox for testing
Config.set_sandbox_disabled(True)

# Setup
tool_manager = ToolManager()
message_history = MessageHistory()
tool_executor = ToolExecutor(tool_manager, message_history)

# Create a temp file
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    f.write("Line 1\nLine 2\nLine 3 to replace\nLine 4\n")
    temp_path = f.name

try:
    # Mark file as read
    FileAccessTracker.record_read(temp_path)
    
    # Create tool call
    tool_call = {
        "id": "test123",
        "function": {
            "name": "edit_file",
            "arguments": json.dumps({
                'path': temp_path,
                'old_string': 'Line 3 to replace',
                'new_string': 'Line 3 was replaced'
            })
        }
    }
    
    # Mock input to auto-approve
    input_responses = ['y']
    
    def mock_input(prompt):
        return input_responses.pop(0) if input_responses else 'y'
    
    import builtins
    builtins.input = mock_input
    
    # Execute the single tool call
    result = tool_executor._execute_single_tool_call(tool_call)
    print("\n=== TOOL EXECUTION COMPLETED ===")
    print(f"Result: {result}")
    
finally:
    os.unlink(temp_path)
    # Restore original input
    import builtins
    if hasattr(builtins, '_original_input'):
        builtins.input = builtins._original_input