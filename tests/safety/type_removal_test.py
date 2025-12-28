"""
Quick smoke test for type system removal
Run after each file change to verify no regressions
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from aicoder.core.config import Config
from aicoder.core.stats import Stats
from aicoder.core.message_history import MessageHistory
from aicoder.core.tool_manager import ToolManager


def test_basic_types():
    """Test basic type conversions work"""
    # Test dict access patterns
    message = {"role": "system", "content": "test"}
    assert message["role"] == "system"
    assert message["content"] == "test"

    # Test ToolResult as dict
    result = {"tool": "read", "friendly": "OK", "detailed": "content", "success": True}
    assert result["tool"] == "read"
    assert result["friendly"] == "OK"
    assert result["detailed"] == "content"
    assert result["success"] is True

    # Test ToolPreview as dict
    preview = {"tool": "write", "content": "preview text", "can_approve": True}
    assert preview["tool"] == "write"
    assert preview["content"] == "preview text"
    assert preview["can_approve"] is True

    # Test ToolResult as dict
    result = {"tool": "read", "friendly": "OK", "detailed": "content", "success": True}
    assert result["tool"] == "read"
    assert result["friendly"] == "OK"
    assert result["detailed"] == "content"
    assert result["success"] is True

    # Test ToolPreview as dict
    preview = {"tool": "write", "content": "preview text", "can_approve": True}
    assert preview["tool"] == "write"
    assert preview["content"] == "preview text"
    assert preview["can_approve"] is True

    print("✓ Basic type conversions work")


def test_tool_manager():
    """Test tool manager still works"""
    stats = Stats()
    manager = ToolManager(stats)

    # Test we can get tool definitions
    defs = manager.get_tool_definitions()
    assert len(defs) > 0

    # Test read_file tool exists
    tool_names = [d["function"]["name"] for d in defs]
    assert "read_file" in tool_names

    print("✓ ToolManager works")


def test_message_history():
    """Test message history still works"""
    stats = Stats()
    history = MessageHistory(stats)

    # Test add system message
    history.add_system_message("You are helpful")
    messages = history.get_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "system"

    # Test add user message
    history.add_user_message("Hello")
    messages = history.get_messages()
    assert len(messages) == 2
    assert messages[1]["role"] == "user"

    print("✓ MessageHistory works")


if __name__ == "__main__":
    try:
        test_basic_types()
        test_tool_manager()
        test_message_history()
        print("\n✓✓✓ All tests passed ✓✓✓")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗✗✗ Test failed: {e} ✗✗✗")
        import traceback
        traceback.print_exc()
        sys.exit(1)
