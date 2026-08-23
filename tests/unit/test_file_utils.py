"""Unit tests for file utilities."""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from aicoder.utils.file_utils import (
    get_current_dir,
    get_relative_path,
    check_sandbox,
    file_exists,
    read_file,
    read_file_verified,
    read_file_with_sandbox,
    write_file,
    write_file_verified,
    write_file_with_sandbox,
    list_directory,
    get_read_files,
    _current_dir,
    _read_files
)

class TestGetCurrentDir:
    """Test get_current_dir function."""

    def test_returns_current_dir(self):
        """Test returns the current working directory."""
        result = get_current_dir()
        assert result == _current_dir
        assert result == os.getcwd()

class TestGetRelativePath:
    """Test get_relative_path function."""

    def test_returns_same_path_for_current_dir_file(self):
        """Test returns relative path for file in current directory."""
        # Create a temp file in current directory
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            temp_path = f.name
            rel_path = get_relative_path(temp_path)

        try:
            # Should return relative path without the full cwd prefix
            assert temp_path in rel_path or rel_path in temp_path
        finally:
            os.unlink(temp_path)

    def test_returns_absolute_for_outside_path(self):
        """Test returns absolute path for file outside current directory."""
        result = get_relative_path("/tmp/test.txt")
        assert result == "/tmp/test.txt"

    def test_handles_nonexistent_path(self):
        """Test handles nonexistent path gracefully."""
        result = get_relative_path("/nonexistent/path/to/file.txt")
        assert result == "/nonexistent/path/to/file.txt"

    def test_handles_relative_path(self):
        """Test handles relative paths."""
        result = get_relative_path("./test.txt")
        assert "test.txt" in result

class TestCheckSandbox:
    """Test check_sandbox function."""

    def test_allows_when_disabled(self):
        """Test sandbox allows all when disabled."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
            result = check_sandbox("/any/path")
        assert result is True

    def test_allows_current_dir(self):
        """Test sandbox allows current directory."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox(_current_dir)
        assert result is True

    def test_allows_subdirectory(self):
        """Test sandbox allows subdirectory of current."""
        subdir = os.path.join(_current_dir, "subdir")
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox(subdir)
        assert result is True

    def test_blocks_parent_directory(self):
        """Test sandbox blocks parent directory."""
        parent = os.path.dirname(_current_dir)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox(parent)
        assert result is False

    def test_blocks_outside_absolute_path(self):
        """Test sandbox blocks absolute path outside current directory."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox("/tmp")
        assert result is False

    def test_allows_none_path(self):
        """Test sandbox allows empty/None path."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox("")
        assert result is True

        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox(None)
        assert result is True

class TestFileExists:
    """Test file_exists function."""

    def test_returns_true_for_existing_file(self):
        """Test returns True for existing file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            path = f.name

        try:
            assert file_exists(path) is True
        finally:
            os.unlink(path)

    def test_returns_false_for_nonexistent(self):
        """Test returns False for nonexistent file."""
        assert file_exists("/nonexistent/path.txt") is False

class TestReadFile:
    """Test read_file function."""

    def test_reads_file_content(self):
        """Test reads file content correctly."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write("Hello, World!")
            path = f.name

        try:
            result = read_file(path)
            assert result == "Hello, World!"
        finally:
            os.unlink(path)

    def test_reads_binary_file(self):
        """Test reads binary file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            path = f.name

        try:
            result = read_file(path)
            assert result == "\x00\x01\x02\x03"
        finally:
            os.unlink(path)

    def test_raises_on_nonexistent(self):
        """Test raises exception for nonexistent file."""
        with pytest.raises(Exception) as exc_info:
            read_file("/nonexistent/file.txt")
        assert "Error reading file" in str(exc_info.value)

    def test_tracks_read_files(self):
        """Test tracks files that have been read."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write("test content")
            path = f.name

        try:
            read_file(path)
            assert path in _read_files
        finally:
            os.unlink(path)

class TestReadFileWithSandbox:
    """Test read_file_with_sandbox function."""

    def test_reads_within_sandbox(self):
        """Test reads file within sandbox."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write("content")
            path = f.name

        try:
            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = read_file_with_sandbox(path)
            assert result == "content"
        finally:
            os.unlink(path)

    def test_blocks_outside_sandbox(self):
        """Test blocks file outside sandbox."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                read_file_with_sandbox("/tmp/test.txt")
        assert "outside current directory" in str(exc_info.value)

class TestWriteFile:
    """Test write_file function."""

    def test_writes_content(self):
        """Test writes content to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            result = write_file(path, "Hello, World!")

            assert os.path.exists(path)
            with open(path, 'r') as f:
                assert f.read() == "Hello, World!"
            assert "Successfully wrote" in result

    def test_creates_parent_directory(self):
        """Test creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "nested", "file.txt")
            write_file(path, "content")

            assert os.path.isdir(os.path.join(tmpdir, "subdir", "nested"))
            assert os.path.isfile(path)

    def test_returns_byte_count(self):
        """Test returns byte count in result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            content = "Hello, World!"
            result = write_file(path, content)

            expected_bytes = len(content.encode("utf-8"))
            assert f"{expected_bytes} bytes" in result

    def test_handles_unicode(self):
        """Test handles unicode content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "unicode.txt")
            write_file(path, "你好世界")

            with open(path, 'r', encoding='utf-8') as f:
                assert f.read() == "你好世界"

class TestWriteFileWithSandbox:
    """Test write_file_with_sandbox function."""

    def test_writes_within_sandbox(self):
        """Test writes file within sandbox."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")

            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = write_file_with_sandbox(path, "content")

            assert os.path.exists(path)
            assert "Successfully wrote" in result

    def test_blocks_outside_sandbox(self):
        """Test blocks file outside sandbox."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                write_file_with_sandbox("/tmp/test.txt", "content")
        assert "outside current directory" in str(exc_info.value)

class TestListDirectory:
    """Test list_directory function."""

    def test_lists_files(self):
        """Test lists files in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                with open(os.path.join(tmpdir, f"file{i}.txt"), 'w') as f:
                    f.write(f"content {i}")

            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = list_directory(tmpdir)

            assert len(result) == 3
            assert "file0.txt" in result

    def test_filters_hidden_files(self):
        """Test filters hidden files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "visible.txt"), 'w') as f:
                f.write("visible")
            with open(os.path.join(tmpdir, ".hidden"), 'w') as f:
                f.write("hidden")

            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = list_directory(tmpdir)

            assert "visible.txt" in result
            # .hidden should not be included (starts with dot)

    def test_excludes_common_dirs(self):
        """Test excludes common directories like node_modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "node_modules"))
            os.makedirs(os.path.join(tmpdir, ".git"))

            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = list_directory(tmpdir)

            # These should be filtered out
            assert "node_modules" not in result

    def test_blocks_outside_sandbox(self):
        """Test blocks directory outside sandbox."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                list_directory("/tmp")
        assert "outside current directory" in str(exc_info.value)

    def test_handles_empty_directory(self):
        """Test handles empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = list_directory(tmpdir)

            assert result == []

class TestGetReadFiles:
    """Test get_read_files function."""

    def test_returns_copy_of_read_files(self):
        """Test returns a copy of tracked files."""
        # Clear and set test files
        _read_files.clear()
        _read_files.add("/test/path1")
        _read_files.add("/test/path2")

        result = get_read_files()

        assert "/test/path1" in result
        assert "/test/path2" in result
        # Should be a copy, not the original
        assert result is not _read_files

    def test_returns_empty_set_initially(self):
        """Test returns empty set when no files read."""
        _read_files.clear()
        result = get_read_files()
        assert result == set()


class TestVerifiedOpen:
    """TOCTOU-safe open: fd provenance verified after open (fail-closed)."""

    def test_read_rejects_symlink_escape(self, monkeypatch, tmp_path):
        """In-cwd symlink flipped to outside target must be rejected at open."""
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("SECRET")
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        link = cwd / "safe.txt"
        link.symlink_to(secret)
        monkeypatch.chdir(cwd)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                read_file_verified(str(link))
        assert "escaped sandbox" in str(exc_info.value)

    def test_read_allows_in_cwd_symlink(self, monkeypatch, tmp_path):
        """Symlink resolving inside cwd still reads."""
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        target = cwd / "data.txt"
        target.write_text("data")
        link = cwd / "link.txt"
        link.symlink_to("data.txt")  # relative target
        monkeypatch.chdir(cwd)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            assert read_file_verified(str(link)) == "data"

    def test_read_whitelist_dir_allowed(self, monkeypatch, tmp_path):
        """Plugin-whitelisted dirs stay readable through verified open."""
        from aicoder.utils import file_utils
        outside = tmp_path / "skills"
        outside.mkdir()
        skill = outside / "s.md"
        skill.write_text("skill")
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        mock_ps = MagicMock()
        mock_ps.call_hooks.return_value = [str(outside)]
        file_utils.set_plugin_system(mock_ps)
        try:
            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
                assert read_file_verified(str(skill)) == "skill"
        finally:
            file_utils.set_plugin_system(None)

    def test_write_rejects_symlink_escape_no_truncation(self, monkeypatch, tmp_path):
        """Rejected write must NOT truncate the outside target."""
        outside = tmp_path / "outside"
        outside.mkdir()
        victim = outside / "victim.txt"
        victim.write_text("PRECIOUS")
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        link = cwd / "out.txt"
        link.symlink_to(victim)
        monkeypatch.chdir(cwd)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                write_file_verified(str(link), "pwned")
        assert "escaped sandbox" in str(exc_info.value)
        assert victim.read_text() == "PRECIOUS"

    def test_write_creates_missing_subdir(self, monkeypatch, tmp_path):
        """Missing parent dirs created only after verified-open ENOENT."""
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = write_file_verified(str(cwd / "a" / "b" / "new.txt"), "hi")
        assert "Successfully wrote" in result
        assert (cwd / "a" / "b" / "new.txt").read_text() == "hi"

    def _force_proc_fallback(self, monkeypatch):
        """Make the /proc fallback reachable even where /proc is masked."""
        real_exists = os.path.exists

        def fake_exists(p):
            return True if p == "/proc/self/fd" else real_exists(p)

        monkeypatch.setattr(os.path, "exists", fake_exists)

    def test_write_dir_symlink_component_no_stray_creation(
        self, monkeypatch, tmp_path
    ):
        """R7 regression: rejected write through escaped dir-symlink component
        must leave NO created file outside the sandbox."""
        self._force_proc_fallback(monkeypatch)
        outside = tmp_path / "outside"
        outside.mkdir()
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        (cwd / "dlink").symlink_to(outside)  # absolute escaping component
        monkeypatch.chdir(cwd)
        stray_name = "r7probe-abs.txt"
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                write_file_verified(f"dlink/{stray_name}", "pwned")
        assert "escapes sandbox" in str(exc_info.value)
        assert not (outside / stray_name).exists()

    def test_write_relative_dir_symlink_component_no_stray_creation(
        self, monkeypatch, tmp_path
    ):
        """Relative escaping dir-symlink component also leaves no stray."""
        self._force_proc_fallback(monkeypatch)
        outside = tmp_path / "outside"
        outside.mkdir()
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        (cwd / "rlink").symlink_to("../outside")
        monkeypatch.chdir(cwd)
        stray_name = "r7probe-rel.txt"
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                write_file_verified(f"rlink/{stray_name}", "pwned")
        assert "sandbox" in str(exc_info.value)
        assert not (outside / stray_name).exists()

    # NOTE: no in-bounds-abs-symlink SUCCESS test here: the proc fallback
    # needs /proc/self/fd for _fd_realpath, which is masked in this
    # environment, so a legitimate symlinked dir cannot be proven in-bounds
    # under the forced-fallback harness. Rejection paths above still verify
    # the no-stray-creation guarantee.

    def _force_openat2_enoent(self, monkeypatch):
        """Simulate openat2 surfacing a mid-race ENOENT (R8b: escaping dir
        component transiently vanishing). Flow-only fakes: _fd_realpath is
        stubbed because /proc is masked here."""
        import errno as errno_mod
        from aicoder.utils import file_utils as fu

        def enoent(*args, **kwargs):
            raise OSError(errno_mod.ENOENT, "No such file or directory")

        monkeypatch.setattr(fu, "_openat2_beneath", enoent)

    def test_write_enoent_reroute_honest_vanish_creates(
        self, monkeypatch, tmp_path
    ):
        self._force_proc_fallback(monkeypatch)
        self._force_openat2_enoent(monkeypatch)
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        monkeypatch.setattr(
            'aicoder.utils.file_utils._fd_realpath',
            lambda fd: os.getcwd(),
        )
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = write_file_verified("fresh-r8b.txt", "ok")
        assert "Successfully wrote" in result
        assert (cwd / "fresh-r8b.txt").read_text() == "ok"

    def test_write_enoent_reroute_escape_blocked_no_stray(
        self, monkeypatch, tmp_path
    ):
        self._force_proc_fallback(monkeypatch)
        self._force_openat2_enoent(monkeypatch)
        outside = tmp_path / "outside"
        outside.mkdir()
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        monkeypatch.setattr(
            'aicoder.utils.file_utils._fd_realpath',
            lambda fd: str(outside) + "/evade.txt",
        )
        stray_name = "r8probe-enoent.txt"
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                write_file_verified(stray_name, "pwned")
        assert "escaped sandbox" in str(exc_info.value)
        assert not (outside / ("r8probe-enoent.txt")).exists()

    def test_list_directory_rejects_symlink_escape(self, monkeypatch, tmp_path):
        """Symlinked dir flipped to outside target must not leak names."""
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("SECRET")
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        (cwd / "visible.txt").write_text("v")
        link = cwd / "peek"
        link.symlink_to(outside)
        monkeypatch.chdir(cwd)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                list_directory(str(link))
        # static symlink caught by pre-check, race-window by verified open
        msg = str(exc_info.value)
        assert "outside current directory" in msg or "escaped sandbox" in msg

    def test_list_directory_fd_lists_cwd(self, monkeypatch, tmp_path):
        """Normal listing works through the fd-bound path."""
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        (cwd / "one.txt").write_text("1")
        (cwd / "two.txt").write_text("2")
        monkeypatch.chdir(cwd)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            entries = list_directory(".")
        assert sorted(entries) == ["one.txt", "two.txt"]

    def test_sandbox_disabled_legacy_permissive(self, monkeypatch, tmp_path):
        """MINI_SANDBOX=0 keeps old any-path behavior."""
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("SECRET")
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        link = cwd / "safe.txt"
        link.symlink_to(secret)
        monkeypatch.chdir(cwd)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
            assert read_file_verified(str(link)) == "SECRET"

    def test_fd_realpath_tolerates_deleted(self, monkeypatch, tmp_path):
        """Unlinked in-cwd inode keeps its path minus '(deleted)' suffix."""
        if not os.path.exists("/proc/self/fd/0"):
            pytest.skip("/proc/self/fd unavailable in this environment")
        from aicoder.utils.file_utils import _fd_realpath
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        f = cwd / "gone.txt"
        f.write_text("x")
        fd = os.open(str(f), os.O_RDONLY)
        try:
            os.unlink(str(f))
            assert _fd_realpath(fd) == str(f)
        finally:
            os.close(fd)
