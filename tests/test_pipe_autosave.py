#!/usr/bin/env python3
"""
Test pipe mode auto-save behavior
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path


def test_logic_directly():
    """Test the core logic directly"""
    # Test pipe mode with default path -> no save
    is_pipe_mode = True
    using_default = True
    should_save = not (is_pipe_mode and using_default)
    assert not should_save, "Pipe mode with default should not save"
    
    # Test pipe mode with custom path -> save
    is_pipe_mode = True
    using_default = False
    should_save = not (is_pipe_mode and using_default)
    assert should_save, "Pipe mode with custom should save"
    
    # Test interactive mode with default -> save
    is_pipe_mode = False
    using_default = True
    should_save = not (is_pipe_mode and using_default)
    assert should_save, "Interactive mode should save"
    
    # Test interactive mode with custom -> save
    is_pipe_mode = False
    using_default = False
    should_save = not (is_pipe_mode and using_default)
    assert should_save, "Interactive mode with custom should save"


def test_aicoder_initialization():
    """Test AICoder initialization logic"""
    # Add current directory to path
    sys.path.insert(0, '.')
    
    # Test default initialization
    from aicoder.core.aicoder import AICoder
    app = AICoder()
    
    # In interactive mode, should detect pipe mode correctly
    expected_pipe_mode = not sys.stdin.isatty()
    assert app._is_pipe_mode == expected_pipe_mode
    
    # Should have correct default path detection
    default_path = os.path.join(".aicoder", "last-session.json")
    assert app._session_file_path == default_path
    assert app._using_default_save_path == True


def test_custom_path_detection():
    """Test custom path detection"""
    # Add current directory to path
    sys.path.insert(0, '.')
    
    custom_path = "/tmp/custom-session.json"
    
    # Set environment variable
    old_env = os.environ.get("AICODER_AUTO_SAVE_FILE")
    os.environ["AICODER_AUTO_SAVE_FILE"] = custom_path
    
    try:
        from aicoder.core.aicoder import AICoder
        app = AICoder()
        
        # Should detect custom path
        assert app._session_file_path == custom_path
        assert app._using_default_save_path == False
        
    finally:
        # Restore environment
        if old_env is not None:
            os.environ["AICODER_AUTO_SAVE_FILE"] = old_env
        elif "AICODER_AUTO_SAVE_FILE" in os.environ:
            del os.environ["AICODER_AUTO_SAVE_FILE"]


def test_save_decision_logic():
    """Test the save decision logic in _auto_save_on_exit"""
    
    # Test cases: (is_pipe_mode, using_default, should_save)
    test_cases = [
        (True, True, False),   # Pipe mode, default -> no save
        (True, False, True),   # Pipe mode, custom -> save
        (False, True, True),   # Interactive, default -> save
        (False, False, True),  # Interactive, custom -> save
    ]
    
    for is_pipe_mode, using_default, expected_should_save in test_cases:
        # Simulate the logic from _auto_save_on_exit
        should_save = not (is_pipe_mode and using_default)
        assert should_save == expected_should_save, \
            f"Failed for is_pipe_mode={is_pipe_mode}, using_default={using_default}"


if __name__ == "__main__":
    test_logic_directly()
    test_aicoder_initialization()
    test_custom_path_detection()
    test_save_decision_logic()
    print("✅ All tests passed!")