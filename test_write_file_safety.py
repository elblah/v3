#!/usr/bin/env python3
"""Test write_file safety - should return warning to AI without approval"""

import tempfile
import os
import json
from aicoder.core.tool_executor import ToolExecutor
from aicoder.core.tool_manager import ToolManager
from aicoder.core.message_history import MessageHistory
from aicoder.core.config import Config
from aicoder.core.file_access_tracker import FileAccessTracker
from aicoder.core.stats import Stats

# Disable sandbox for testing
Config.set_sandbox_disabled(True)

# Setup
stats = Stats()
tool_manager = ToolManager(stats)
message_history = MessageHistory(stats)
tool_executor = ToolExecutor(tool_manager, message_history)

# Create a temp file
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    f.write("Existing content\n")
    temp_path = f.name

try:
    # Clear file access tracker
    FileAccessTracker.clear_state()
    
    # Try to write to existing file without reading first
    print("\n=== TEST: Write to existing file without reading ===")
    tool_call = {
        "id": "test123",
        "function": {
            "name": "write_file",
            "arguments": json.dumps({
                'path': temp_path,
                'content': 'New content that should not be written'
            })
        }
    }
    
    # Mock input to not block
    import builtins
    original_input = builtins.input
    builtins.input = lambda prompt: ''
    
    result = tool_executor._execute_single_tool_call(tool_call)
    print(f"\nResult returned to AI: {result}")
    
    # Verify file wasn't changed
    with open(temp_path, 'r') as f:
        actual_content = f.read()
    print(f"File content after attempt: {repr(actual_content)}")
    
    if actual_content == "Existing content\n":
        print("✅ File was NOT changed - safety mechanism worked!")
    else:
        print("❌ File was changed - safety mechanism FAILED!")
    
finally:
    os.unlink(temp_path)
    builtins.input = original_input