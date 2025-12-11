#!/usr/bin/env python3
"""Test edit_file to verify AI receives proper error messages"""

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
from aicoder.core.stats import Stats
stats = Stats()
tool_manager = ToolManager(stats)
message_history = MessageHistory(stats)
tool_executor = ToolExecutor(tool_manager, message_history)

# Create a temp file
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    f.write("Line 1\nLine 2\nLine 3 to replace\nLine 4\n")
    temp_path = f.name

try:
    # Clear file access tracker
    FileAccessTracker.clear_state()
    
    # Test 1: Try to edit without reading first (safety violation)
    print("\n=== TEST 1: Safety violation (no read) ===")
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
    
    # Mock input to not block
    import builtins
    original_input = builtins.input
    builtins.input = lambda prompt: ''
    
    result = tool_executor._execute_single_tool_call(tool_call)
    print(f"Result returned: {result}")
    
    # Test 2: Try to edit non-existent text
    print("\n=== TEST 2: Text not found ===")
    FileAccessTracker.record_read(temp_path)  # Mark as read
    
    tool_call2 = {
        "id": "test456",
        "function": {
            "name": "edit_file",
            "arguments": json.dumps({
                'path': temp_path,
                'old_string': 'Non-existent text',
                'new_string': 'Replacement'
            })
        }
    }
    
    result2 = tool_executor._execute_single_tool_call(tool_call2)
    print(f"Result returned: {result2}")
    
    # Check message history
    print("\n=== MESSAGE HISTORY ===")
    messages = message_history.get_messages()
    for msg in messages[-2:]:  # Last 2 messages
        if isinstance(msg, dict):
            if 'tool_calls' in msg:
                print("Tool call:", msg['tool_calls'])
            elif 'content' in msg:
                if len(msg['content']) > 200:
                    print(f"Content (truncated): {msg['content'][:200]}...")
                else:
                    print(f"Content: {msg['content']}")
            else:
                print("Message:", msg)
        else:
            print(f"Message ({type(msg)}): {msg}")
    
finally:
    os.unlink(temp_path)
    builtins.input = original_input