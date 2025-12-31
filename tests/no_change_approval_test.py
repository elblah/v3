#!/usr/bin/env python3
"""
Test that write_file and edit_file don't require approval when there are no changes
"""

import os
import sys
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aicoder.tools.internal.write_file import generate_preview as write_file_preview
from aicoder.tools.internal.edit_file import generate_preview as edit_file_preview
from aicoder.core.file_access_tracker import FileAccessTracker


# Test directory
TEST_DIR = "./tmp/no_change_approval_test"


def setup_test_dir():
    """Create test directory"""
    os.makedirs(TEST_DIR, exist_ok=True)


def cleanup_test_dir():
    """Remove test directory"""
    shutil.rmtree(TEST_DIR, ignore_errors=True)


def test_write_file_no_changes():
    """Test write_file preview with identical content"""
    print("Testing write_file with identical content...")

    setup_test_dir()

    try:
        test_file = os.path.join(TEST_DIR, "test_no_change.txt")
        test_content = "Hello World\n"

        # Create file
        with open(test_file, 'w') as f:
            f.write(test_content)

        # Mark as read
        FileAccessTracker.record_read(test_file)

        # Generate preview - should show no changes
        preview = write_file_preview({
            "path": test_file,
            "content": test_content  # Same content
        })

        print(f"  can_approve: {preview['can_approve']}")
        print(f"  content snippet: {preview['content'][:50]}...")

        # Should NOT be approvable since no changes
        assert preview['can_approve'] == False, "write_file should not require approval when no changes"
        assert "No changes" in preview['content'], "Preview should mention no changes"
        print("  ✓ write_file correctly returns can_approve=False for no changes")
    finally:
        cleanup_test_dir()


def test_write_file_with_changes():
    """Test write_file preview with different content"""
    print("\nTesting write_file with different content...")

    setup_test_dir()

    try:
        test_file = os.path.join(TEST_DIR, "test_with_changes.txt")
        old_content = "Hello World\n"
        new_content = "Hello Universe\n"

        # Create file
        with open(test_file, 'w') as f:
            f.write(old_content)

        # Mark as read
        FileAccessTracker.record_read(test_file)

        # Generate preview - should show diff
        preview = write_file_preview({
            "path": test_file,
            "content": new_content
        })

        print(f"  can_approve: {preview['can_approve']}")

        # SHOULD be approvable since there are changes
        assert preview['can_approve'] == True, "write_file should require approval when there are changes"
        print("  ✓ write_file correctly returns can_approve=True for changes")
    finally:
        cleanup_test_dir()


def test_edit_file_no_changes():
    """Test edit_file preview with identical old_string"""
    print("\nTesting edit_file with identical content...")

    setup_test_dir()

    try:
        test_file = os.path.join(TEST_DIR, "test_edit_no_change.txt")
        test_content = "Hello World\n"

        # Create file
        with open(test_file, 'w') as f:
            f.write(test_content)

        # Mark as read
        FileAccessTracker.record_read(test_file)

        # Generate preview - try to replace with same content
        preview = edit_file_preview({
            "path": test_file,
            "old_string": "Hello World\n",
            "new_string": "Hello World\n"  # Same content
        })

        print(f"  can_approve: {preview['can_approve']}")

        # Should NOT be approvable since no changes
        assert preview['can_approve'] == False, "edit_file should not require approval when no changes"
        print("  ✓ edit_file correctly returns can_approve=False for no changes")
    finally:
        cleanup_test_dir()


def test_edit_file_with_changes():
    """Test edit_file preview with different content"""
    print("\nTesting edit_file with different content...")

    setup_test_dir()

    try:
        test_file = os.path.join(TEST_DIR, "test_edit_with_changes.txt")
        test_content = "Hello World\n"

        # Create file
        with open(test_file, 'w') as f:
            f.write(test_content)

        # Mark as read
        FileAccessTracker.record_read(test_file)

        # Debug: check if file is tracked
        print(f"  File was read: {FileAccessTracker.was_file_read(test_file)}")

        # Generate preview - replace with different content
        preview = edit_file_preview({
            "path": test_file,
            "old_string": "Hello World\n",
            "new_string": "Hello Universe\n"
        })

        print(f"  can_approve: {preview['can_approve']}")
        print(f"  content snippet: {preview['content'][:100]}...")

        # SHOULD be approvable since there are changes
        assert preview['can_approve'] == True, "edit_file should require approval when there are changes"
        print("  ✓ edit_file correctly returns can_approve=True for changes")
    finally:
        cleanup_test_dir()


def test_write_file_new_file():
    """Test write_file preview for new file"""
    print("\nTesting write_file for new file...")

    setup_test_dir()

    try:
        test_file = os.path.join(TEST_DIR, "new.txt")
        test_content = "Hello World\n"

        # Generate preview - new file
        preview = write_file_preview({
            "path": test_file,
            "content": test_content
        })

        print(f"  can_approve: {preview['can_approve']}")

        # SHOULD be approvable for new file
        assert preview['can_approve'] == True, "write_file should require approval for new file"
        print("  ✓ write_file correctly returns can_approve=True for new file")
    finally:
        cleanup_test_dir()


if __name__ == "__main__":
    print("=" * 60)
    print("Testing no-change approval fixes")
    print("=" * 60)

    try:
        test_write_file_no_changes()
        test_write_file_with_changes()
        test_write_file_new_file()
        test_edit_file_no_changes()
        test_edit_file_with_changes()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
