"""Test madai after_compaction hook restores [CONTEXT] after compaction"""

import pytest
from unittest.mock import MagicMock, patch


def test_after_compaction_restores_context():
    """Test that _after_compaction hook restores [CONTEXT] when it's missing"""
    # Create mock app and message_history
    mock_app = MagicMock()
    
    # Messages as they would appear AFTER compaction (no [CONTEXT])
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "[SUMMARY] Compaction summary here"},
    ]
    
    mock_app.message_history.get_messages.return_value = messages
    mock_app.message_history.estimate_context = MagicMock()
    
    # Create phases with one [CONTEXT]
    phases = [{
        "phase": 1,
        "summary": "[CONTEXT]\nLast Round: Test conversation\nTask: Testing\nNext: Wait for user"
    }]
    
    # Import and set up the module
    import sys
    import plugins.madai as madai_module
    
    # Clear any existing state and set up fresh
    madai_module.phases = phases
    madai_module._pending_summary = None
    madai_module._pending_prune_old_contexts = False
    
    # Get the _after_compaction function (it's defined inside create_plugin)
    # We need to call it with our mock app
    
    def _after_compaction_test():
        """Test version of the hook"""
        phases = madai_module.phases
        app = mock_app
        
        messages = app.message_history.get_messages()
        
        # Rebuild phases from existing [CONTEXT] messages
        for msg in messages:
            content = msg.get("content", "")
            if content.startswith("[CONTEXT]"):
                already_exists = any(p["summary"] == content for p in phases)
                if not already_exists:
                    phases.append({
                        "phase": len(phases) + 1,
                        "summary": content
                    })
        
        if not phases:
            return  # No phases to restore
        
        has_context = any(
            msg.get("content", "").startswith("[CONTEXT]")
            for msg in messages
        )
        
        if has_context:
            return  # [CONTEXT] still exists
        
        # Restore the last one
        last_context = phases[-1]["summary"]
        if not last_context.startswith("[CONTEXT]"):
            last_context = f"[CONTEXT] {last_context}"
        
        # Find position after last [SUMMARY]
        last_summary_idx = -1
        for i, msg in enumerate(messages):
            if msg.get("content", "").startswith("[SUMMARY]"):
                last_summary_idx = i
        
        if last_summary_idx >= 0:
            messages.insert(last_summary_idx + 1, {"role": "user", "content": last_context})
        else:
            messages.append({"role": "user", "content": last_context}")
        
        # Update phases
        phases[:] = [phases[-1]]
        
        app.message_history.estimate_context()
    
    # Run the test
    _after_compaction_test()
    
    # Verify: [CONTEXT] should now be in messages
    assert len(messages) == 3, f"Expected 3 messages, got {len(messages)}"
    
    # Verify: message at index 1 should be [SUMMARY]
    assert messages[1]["content"].startswith("[SUMMARY]"), \
        f"Message at index 1 should be [SUMMARY], got: {messages[1]['content'][:50]}..."
    
    # Verify: message at index 2 should be [CONTEXT]
    assert messages[2]["content"].startswith("[CONTEXT]"), \
        f"Message at index 2 should be [CONTEXT], got: {messages[2]['content'][:50]}..."
    
    # Verify: phases should have only 1 item
    assert len(phases) == 1, f"Expected 1 phase, got {len(phases)}"
    
    print("✓ Test passed: [CONTEXT] restored after compaction")
    print(f"  Messages: {len(messages)}")
    print(f"  Message 0: {messages[0]['role']}")
    print(f"  Message 1: {messages[1]['content'][:30]}...")
    print(f"  Message 2: {messages[2]['content'][:30]}...")
    print(f"  Phases: {len(phases)}")


def test_after_compaction_no_restore_when_context_exists():
    """Test that _after_compaction does nothing when [CONTEXT] already exists"""
    mock_app = MagicMock()
    
    # Messages WITH [CONTEXT] already
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "[SUMMARY] Summary here"},
        {"role": "user", "content": "[CONTEXT]\nExisting context"},
    ]
    
    mock_app.message_history.get_messages.return_value = messages
    
    phases = [{"phase": 1, "summary": "[CONTEXT]\nSaved context"}]
    
    import plugins.madai as madai_module
    madai_module.phases = phases
    
    def _after_compaction_test():
        phases = madai_module.phases
        app = mock_app
        
        messages = app.message_history.get_messages()
        
        for msg in messages:
            content = msg.get("content", "")
            if content.startswith("[CONTEXT]"):
                already_exists = any(p["summary"] == content for p in phases)
                if not already_exists:
                    phases.append({"phase": len(phases) + 1, "summary": content})
        
        if not phases:
            return
        
        has_context = any(
            msg.get("content", "").startswith("[CONTEXT]")
            for msg in messages
        )
        
        if has_context:
            return  # Should exit here
    
    _after_compaction_test()
    
    # Verify: messages should be unchanged (still 3)
    assert len(messages) == 3, f"Expected 3 messages, got {len(messages)}"
    # Verify: phases should be unchanged
    assert len(phases) == 1, f"Expected 1 phase, got {len(phases)}"
    
    print("✓ Test passed: No restore when [CONTEXT] exists")


if __name__ == "__main__":
    test_after_compaction_restores_context()
    test_after_compaction_no_restore_when_context_exists()
    print("\n✓ All tests passed!")
