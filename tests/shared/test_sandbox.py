"""
Shared tests for sandbox behavior.

These tests verify the centralized symlink-safe check in
`aicoder.utils.file_utils.check_sandbox`, which all file tools
(read, write, edit, list, grep) use.
"""

import os
import pytest
from unittest.mock import patch

import aicoder.utils.file_utils as fu
from aicoder.core.config import Config
from aicoder.utils.file_utils import check_sandbox


@pytest.fixture
def sandbox_on():
    with patch.object(Config, 'sandbox_disabled', return_value=False):
        yield


class TestSandboxBehavior:
    """Test sandbox enforcement."""

    def test_sandbox_disabled(self):
        with patch.object(Config, 'sandbox_disabled', return_value=True):
            assert check_sandbox("/some/path") is True

    def test_empty_path(self, sandbox_on):
        assert check_sandbox("") is True

    def test_path_within_current_dir(self, sandbox_on):
        with patch('os.getcwd', return_value='/home/user/project'):
            assert check_sandbox('/home/user/project/file.txt', print_message=False) is True

    def test_path_outside_current_dir(self, sandbox_on):
        with patch('os.getcwd', return_value='/home/user/project'):
            assert check_sandbox('/etc/passwd', print_message=False) is False

    def test_path_equal_to_current_dir(self, sandbox_on):
        with patch('os.getcwd', return_value='/home/user/project'):
            assert check_sandbox('/home/user/project', print_message=False) is True

    def test_subdirectory_allowed(self, sandbox_on):
        with patch('os.getcwd', return_value='/home/user/project'):
            assert check_sandbox('/home/user/project/subdir/file.txt', print_message=False) is True

    def test_deeply_nested_subdirectory_allowed(self, sandbox_on):
        with patch('os.getcwd', return_value='/home/user/project'):
            assert check_sandbox('/home/user/project/a/b/c/file.txt', print_message=False) is True

    def test_parent_directory_denied(self, sandbox_on):
        with patch('os.getcwd', return_value='/home/user/project'):
            assert check_sandbox('/home/user', print_message=False) is False

    def test_path_traversal_denied(self, sandbox_on):
        with patch('os.getcwd', return_value='/home/user/project'):
            assert check_sandbox('/home/user/project/../outside', print_message=False) is False

    def test_lexical_prefix_does_not_spoof(self, sandbox_on):
        """Sibling dir sharing a prefix must be denied (was the old bug)."""
        with patch('os.getcwd', return_value='/home/user/project'):
            assert check_sandbox('/home/user/project-evil/file.txt', print_message=False) is False


class TestSandboxSymlinks:
    """Symlink-safety regression tests against the real filesystem."""

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        """Real temp dir as cwd, with an outside dir."""
        outside = tmp_path / "outside"
        outside.mkdir()
        proj = tmp_path / "project"
        (proj / "sub").mkdir(parents=True)
        monkeypatch.chdir(proj)
        return proj, outside

    def test_symlink_to_outside_denied(self, project, sandbox_on):
        proj, outside = project
        os.symlink(str(outside), str(proj / "link"))
        assert check_sandbox("link", print_message=False) is False
        assert check_sandbox("link/file.txt", print_message=False) is False

    def test_symlink_to_root_denied(self, project, sandbox_on):
        proj, _ = project
        os.symlink("/", str(proj / "rootlink"))
        assert check_sandbox("rootlink/etc/passwd", print_message=False) is False

    def test_internal_symlink_allowed(self, project, sandbox_on):
        proj, _ = project
        (proj / "sub" / "file.txt").write_text("x")
        os.symlink(str(proj / "sub"), str(proj / "sublink"))
        assert check_sandbox("sublink/file.txt", print_message=False) is True

    def test_new_file_write_allowed(self, project, sandbox_on):
        """Non-existent tail must resolve via parent (writes to new files)."""
        assert check_sandbox("sub/newfile.txt", print_message=False) is True

    def test_traversal_through_symlink_denied(self, project, sandbox_on):
        proj, outside = project
        os.symlink(str(outside), str(proj / "sub" / "link"))
        assert check_sandbox("sub/link/../../../etc/passwd", print_message=False) is False


class FakeWhitelistSystem:
    """Fake plugin system whose on_file_sandbox_whitelist hook returns dirs."""

    def __init__(self, results):
        self._results = results

    def call_hooks(self, event, *args, **kwargs):
        assert event == "on_file_sandbox_whitelist"
        return list(self._results)


class TestSandboxWhitelist:
    """Plugin-whitelisted dirs grant read-only access outside cwd."""

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        proj = tmp_path / "project"
        proj.mkdir()
        (proj / "sub").mkdir()
        outside = tmp_path / "skills"
        (outside / "dtx").mkdir(parents=True)
        (outside / "dtx" / "SKILL.md").write_text("skill")
        monkeypatch.chdir(proj)
        return proj, outside

    @pytest.fixture
    def whitelist(self, project, monkeypatch):
        _, outside = project
        ps = FakeWhitelistSystem([[str(outside)]])
        monkeypatch.setattr(fu, "_plugin_system", ps)
        return ps

    def test_whitelisted_path_allowed(self, project, whitelist, sandbox_on):
        _, outside = project
        assert check_sandbox(str(outside / "dtx" / "SKILL.md"), print_message=False) is True

    def test_whitelisted_dir_root_allowed(self, project, whitelist, sandbox_on):
        _, outside = project
        assert check_sandbox(str(outside), print_message=False) is True

    def test_outside_whitelist_denied(self, project, whitelist, sandbox_on):
        assert check_sandbox("/etc/passwd", print_message=False) is False

    def test_lexical_prefix_of_whitelist_denied(self, project, whitelist, sandbox_on):
        _, outside = project
        sibling = outside.parent / (outside.name + "-evil")
        assert check_sandbox(str(sibling / "SKILL.md"), print_message=False) is False

    def test_whitelist_write_denied(self, project, whitelist, sandbox_on):
        """Whitelist is read-only: write tools must never use it."""
        _, outside = project
        assert check_sandbox(str(outside / "dtx" / "SKILL.md"), print_message=False,
                             write=True) is False

    def test_symlink_inside_whitelist_to_outside_denied(self, project, whitelist, sandbox_on):
        """Symlink-safe: link within whitelisted dir pointing elsewhere is denied."""
        _, outside = project
        secret = outside.parent / "secret"
        secret.mkdir()
        os.symlink(str(secret), str(outside / "leak"))
        assert check_sandbox(str(outside / "leak" / "f"), print_message=False) is False

    def test_no_plugin_system_denied(self, project, monkeypatch, sandbox_on):
        monkeypatch.setattr(fu, "_plugin_system", None)
        _, outside = project
        assert check_sandbox(str(outside / "dtx" / "SKILL.md"), print_message=False) is False

    def test_hook_returning_none_denied(self, project, monkeypatch, sandbox_on):
        monkeypatch.setattr(fu, "_plugin_system", FakeWhitelistSystem([None]))
        _, outside = project
        assert check_sandbox(str(outside / "dtx" / "SKILL.md"), print_message=False) is False

    def test_hook_string_result_allowed(self, project, monkeypatch, sandbox_on):
        """A hook may return a single string instead of a list."""
        _, outside = project
        monkeypatch.setattr(fu, "_plugin_system", FakeWhitelistSystem([str(outside)]))
        assert check_sandbox(str(outside / "dtx" / "SKILL.md"), print_message=False) is True

    def test_write_inside_cwd_still_allowed(self, project, whitelist, sandbox_on):
        proj, _ = project
        assert check_sandbox("sub/new.txt", print_message=False, write=True) is True
