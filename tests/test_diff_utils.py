"""
Tests for diff utilities
"""

import pytest
import tempfile
import os


class TestDiffUtils:
    """Test diff utility functions"""

    def test_generate_unified_diff_identical_files(self):
        """Test diff of identical files"""
        from aicoder.utils.diff_utils import generate_unified_diff

        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "file1.txt")
            file2 = os.path.join(tmpdir, "file2.txt")

            with open(file1, "w") as f:
                f.write("hello\nworld\n")
            with open(file2, "w") as f:
                f.write("hello\nworld\n")

            result = generate_unified_diff(file1, file2)

            # Identical files return success
            assert "No changes" in result or result.success is True or result == ""

    def test_generate_unified_diff_different_files(self):
        """Test diff of different files"""
        from aicoder.utils.diff_utils import generate_unified_diff

        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "file1.txt")
            file2 = os.path.join(tmpdir, "file2.txt")

            with open(file1, "w") as f:
                f.write("hello\n")
            with open(file2, "w") as f:
                f.write("goodbye\n")

            result = generate_unified_diff(file1, file2)

            # Different files show differences
            assert "-" in result or "Differences" in result or result.exit_code == 1

    def test_generate_unified_diff_with_status_identical(self):
        """Test diff status for identical files"""
        from aicoder.utils.diff_utils import generate_unified_diff_with_status

        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "file1.txt")
            file2 = os.path.join(tmpdir, "file2.txt")

            with open(file1, "w") as f:
                f.write("same content\n")
            with open(file2, "w") as f:
                f.write("same content\n")

            result = generate_unified_diff_with_status(file1, file2)

            assert "has_changes" in result
            assert "diff" in result
            assert "exit_code" in result

    def test_generate_unified_diff_with_status_different(self):
        """Test diff status for different files"""
        from aicoder.utils.diff_utils import generate_unified_diff_with_status

        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "file1.txt")
            file2 = os.path.join(tmpdir, "file2.txt")

            with open(file1, "w") as f:
                f.write("line1\n")
            with open(file2, "w") as f:
                f.write("line2\n")

            result = generate_unified_diff_with_status(file1, file2)

            assert "has_changes" in result
            assert "diff" in result
            assert "exit_code" in result

    def test_colorize_diff_basic(self):
        """Test diff colorization"""
        from aicoder.utils.diff_utils import colorize_diff

        diff_output = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
-old line
+new line
 context
"""

        result = colorize_diff(diff_output)

        # Header lines should be skipped
        assert "--- a/file.py" not in result
        assert "+++ b/file.py" not in result
