#!/usr/bin/env python3
"""Quick test for edit_file diff coloring and path display"""

import tempfile
import os
import json
from aicoder.tools.internal.edit_file import generate_preview
from aicoder.core.file_access_tracker import FileAccessTracker
from aicoder.core.config import Config

# Disable sandbox for testing
Config.set_sandbox_disabled(True)

# Create a temp file
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    f.write("Line 1\nLine 2\nLine 3 to replace\nLine 4\n")
    temp_path = f.name

try:
    # Mark file as read
    FileAccessTracker.record_read(temp_path)
    
    # Generate preview
    args = {
        'path': temp_path,
        'old_string': 'Line 3 to replace',
        'new_string': 'Line 3 was replaced'
    }
    
    preview = generate_preview(args)
    print("=== PREVIEW RESULT ===")
    print(f"Can approve: {preview.can_approve}")
    print(f"Content:\n{preview.content}")
    
finally:
    os.unlink(temp_path)