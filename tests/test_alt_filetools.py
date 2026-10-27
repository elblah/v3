"""Tests for the alt file tools plugin (AICODER_ALT_FILETOOLS)."""

import os
from unittest.mock import patch

import pytest

from aicoder.core.config import Config
from aicoder.plugins import alt_filetools as af


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Run inside a temp cwd with the sandbox containment check disabled."""
    monkeypatch.chdir(tmp_path)
    with patch.object(Config, "sandbox_disabled", return_value=True):
        yield tmp_path


def _write(path, text="data"):
    path.write_text(text)
    return path


class TestMovePath:
    def test_move_file(self, workdir):
        src = _write(workdir / "a.txt")
        result = af.move_path({"source": "a.txt", "destination": "b.txt"})
        assert "Moved file" in result["detailed"]
        assert not src.exists()
        assert (workdir / "b.txt").read_text() == "data"

    def test_move_into_subdir(self, workdir):
        _write(workdir / "a.txt")
        (workdir / "sub").mkdir()
        result = af.move_path({"source": "a.txt", "destination": "sub/a.txt"})
        assert "Moved file" in result["detailed"]
        assert (workdir / "sub" / "a.txt").exists()

    def test_move_directory(self, workdir):
        (workdir / "d").mkdir()
        _write(workdir / "d" / "f.txt")
        result = af.move_path({"source": "d", "destination": "e"})
        assert "Moved directory" in result["detailed"]
        assert (workdir / "e" / "f.txt").exists()

    def test_refuses_existing_destination(self, workdir):
        _write(workdir / "a.txt")
        _write(workdir / "b.txt", "keep")
        result = af.move_path({"source": "a.txt", "destination": "b.txt"})
        assert "destination exists" in result["detailed"]
        assert (workdir / "b.txt").read_text() == "keep"

    def test_overwrite_flag_as_string(self, workdir):
        _write(workdir / "a.txt", "new")
        _write(workdir / "b.txt", "old")
        result = af.move_path(
            {"source": "a.txt", "destination": "b.txt", "overwrite": "true"}
        )
        assert "Moved" in result["detailed"]
        assert (workdir / "b.txt").read_text() == "new"

    def test_refuses_refuses_missing_source(self, workdir):
        result = af.move_path({"source": "nope", "destination": "x"})
        assert "source not found" in result["detailed"]

    def test_refuses_directory_overwrite(self, workdir):
        (workdir / "d").mkdir()
        (workdir / "e").mkdir()
        result = af.move_path({"source": "d", "destination": "e", "overwrite": True})
        assert "overwrite a directory" in result["detailed"]
        assert (workdir / "d").is_dir()

    def test_refuses_move_into_itself(self, workdir):
        (workdir / "d").mkdir()
        result = af.move_path({"source": "d", "destination": "d/inner"})
        assert "inside itself" in result["detailed"]

    def test_refuses_cwd(self, workdir):
        _write(workdir / "a.txt")
        result = af.move_path({"source": ".", "destination": "b"})
        assert "invalid target name" in result["detailed"] or "refusing" in result["detailed"]

    def test_requires_arguments(self, workdir):
        result = af.move_path({"source": "a"})
        assert "'destination' is required" in result["detailed"]


class TestCopyPath:
    def test_copy_file(self, workdir):
        _write(workdir / "a.txt")
        result = af.copy_path({"source": "a.txt", "destination": "b.txt"})
        assert "Copied file" in result["detailed"]
        assert (workdir / "a.txt").exists()
        assert (workdir / "b.txt").read_text() == "data"

    def test_copy_preserves_mode(self, workdir):
        src = _write(workdir / "run.sh")
        os.chmod(src, 0o755)
        af.copy_path({"source": "run.sh", "destination": "run2.sh"})
        assert os.stat(workdir / "run2.sh").st_mode & 0o777 == 0o755

    def test_copy_directory_recursive(self, workdir):
        (workdir / "d" / "nested").mkdir(parents=True)
        _write(workdir / "d" / "f.txt")
        _write(workdir / "d" / "nested" / "g.txt")
        result = af.copy_path({"source": "d", "destination": "d2"})
        assert "Copied directory" in result["detailed"]
        assert (workdir / "d2" / "nested" / "g.txt").read_text() == "data"

    def test_copy_symlink_copied_as_link(self, workdir):
        _write(workdir / "a.txt")
        os.symlink("a.txt", workdir / "link")
        af.copy_path({"source": "link", "destination": "link2"})
        assert os.path.islink(workdir / "link2")
        assert os.readlink(workdir / "link2") == "a.txt"

    def test_symlink_to_outside_is_not_followed(self, workdir, tmp_path):
        outside = tmp_path.parent / "outside_target.txt"
        outside.write_text("secret")
        os.symlink(str(outside), workdir / "link")
        result = af.copy_path({"source": "link", "destination": "link2"})
        assert "Copied symlink" in result["detailed"]
        assert os.path.islink(workdir / "link2")

    def test_refuses_existing_file_destination(self, workdir):
        _write(workdir / "a.txt", "new")
        _write(workdir / "b.txt", "old")
        result = af.copy_path({"source": "a.txt", "destination": "b.txt"})
        assert "destination exists" in result["detailed"]
        assert (workdir / "b.txt").read_text() == "old"

    def test_overwrite_replaces_file(self, workdir):
        _write(workdir / "a.txt", "new")
        _write(workdir / "b.txt", "old")
        af.copy_path({"source": "a.txt", "destination": "b.txt", "overwrite": True})
        assert (workdir / "b.txt").read_text() == "new"

    def test_refuses_copy_into_itself(self, workdir):
        (workdir / "d").mkdir()
        result = af.copy_path({"source": "d", "destination": "d/sub"})
        assert "inside itself" in result["detailed"]


class TestDeletePath:
    def test_delete_file(self, workdir):
        _write(workdir / "a.txt")
        result = af.delete_path({"path": "a.txt"})
        assert "Deleted file" in result["detailed"]
        assert not (workdir / "a.txt").exists()

    def test_delete_empty_directory(self, workdir):
        (workdir / "d").mkdir()
        result = af.delete_path({"path": "d"})
        assert "Deleted empty directory" in result["detailed"]
        assert not (workdir / "d").exists()

    def test_refuses_non_empty_without_recursive(self, workdir):
        (workdir / "d").mkdir()
        _write(workdir / "d" / "f.txt")
        result = af.delete_path({"path": "d"})
        assert "not empty" in result["detailed"]
        assert (workdir / "d" / "f.txt").exists()

    def test_recursive_delete(self, workdir):
        (workdir / "d" / "nested").mkdir(parents=True)
        _write(workdir / "d" / "f.txt")
        result = af.delete_path({"path": "d", "recursive": True})
        assert "Deleted directory" in result["detailed"]
        assert not (workdir / "d").exists()

    def test_symlink_delete_removes_link_only(self, workdir, tmp_path):
        target = _write(tmp_path / "target.txt")
        os.symlink(str(target), workdir / "link")
        result = af.delete_path({"path": "link", "recursive": True})
        assert "Deleted symlink" in result["detailed"]
        assert not os.path.lexists(workdir / "link")
        assert target.exists()

    def test_recursive_delete_does_not_follow_symlinks(self, workdir, tmp_path):
        target_dir = tmp_path / "outside"
        target_dir.mkdir()
        _write(target_dir / "keep.txt")
        (workdir / "d").mkdir()
        os.symlink(str(target_dir), workdir / "d" / "link")
        af.delete_path({"path": "d", "recursive": True})
        assert (target_dir / "keep.txt").exists()

    def test_refuses_missing_path(self, workdir):
        result = af.delete_path({"path": "nope"})
        assert "path not found" in result["detailed"]

    def test_entry_limit_refused_before_deleting(self, workdir, monkeypatch):
        monkeypatch.setattr(af, "MAX_ENTRIES", 2)
        (workdir / "d").mkdir()
        for i in range(4):
            _write(workdir / "d" / f"f{i}.txt")
        result = af.delete_path({"path": "d", "recursive": True})
        assert "refusing to delete" in result["detailed"]
        assert len(list((workdir / "d").iterdir())) == 4


class TestCreateDirectory:
    def test_create_single(self, workdir):
        result = af.create_directory({"path": "new"})
        assert "Created directory" in result["detailed"]
        assert (workdir / "new").is_dir()

    def test_create_nested(self, workdir):
        result = af.create_directory({"path": "a/b/c"})
        assert "Created directory" in result["detailed"]
        assert (workdir / "a" / "b" / "c").is_dir()

    def test_existing_is_ok(self, workdir):
        (workdir / "d").mkdir()
        result = af.create_directory({"path": "d"})
        assert "already exists" in result["detailed"]

    def test_parents_false_refuses_missing_parent(self, workdir):
        result = af.create_directory({"path": "a/b", "parents": False})
        assert "cannot enter" in result["detailed"] or "not found" in result["detailed"]
        assert not (workdir / "a").exists()

    def test_refuses_file_component(self, workdir):
        _write(workdir / "f")
        result = af.create_directory({"path": "f/sub"})
        assert "not a directory" in result["detailed"]


class TestPathInfo:
    def test_file_info(self, workdir):
        _write(workdir / "a.txt", "hello")
        result = af.path_info({"path": "a.txt"})
        assert "type: file" in result["detailed"]
        assert "size: 5 bytes" in result["detailed"]
        assert "mode: 0o" in result["detailed"]

    def test_directory_info(self, workdir):
        (workdir / "d").mkdir()
        _write(workdir / "d" / "f.txt")
        result = af.path_info({"path": "d"})
        assert "type: directory" in result["detailed"]
        assert "entries: 1" in result["detailed"]

    def test_symlink_info_does_not_follow(self, workdir):
        _write(workdir / "a.txt")
        os.symlink("a.txt", workdir / "link")
        result = af.path_info({"path": "link"})
        assert "type: symlink" in result["detailed"]
        assert "symlink target: a.txt" in result["detailed"]
        assert "target exists: yes" in result["detailed"]

    def test_missing(self, workdir):
        result = af.path_info({"path": "nope"})
        assert "path not found" in result["detailed"]


class TestSandbox:
    def test_outside_path_denied_when_sandbox_on(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch.object(Config, "sandbox_disabled", return_value=False):
            result = af.delete_path({"path": "/etc/hostname"})
        text = result["detailed"]
        assert "delete_path:" in text
        assert "outside" in text or "denied" in text or "blocked" in text

    def test_parent_traversal_denied_when_sandbox_on(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "victim.txt"
        outside.write_text("keep")
        with patch.object(Config, "sandbox_disabled", return_value=False):
            result = af.delete_path({"path": "../victim.txt"})
        assert not result["detailed"].startswith("Deleted")
        assert outside.exists()


class TestPluginRegistration:
    def _ctx(self):
        class Ctx:
            def __init__(self):
                self.tools = {}

            def register_tool(self, name, fn, description, parameters,
                              auto_approved=False, format_arguments=None,
                              generate_preview=None):
                self.tools[name] = {
                    "fn": fn,
                    "description": description,
                    "parameters": parameters,
                    "auto_approved": auto_approved,
                    "formatArguments": format_arguments,
                    "generatePreview": generate_preview,
                }

        return Ctx()

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv(af.ENV_FLAG, raising=False)
        ctx = self._ctx()
        af.create_plugin(ctx)
        assert ctx.tools == {}

    def test_registers_tools_when_enabled(self, monkeypatch):
        monkeypatch.setenv(af.ENV_FLAG, "1")
        ctx = self._ctx()
        af.create_plugin(ctx)
        assert set(ctx.tools) == {
            "move_path", "copy_path", "delete_path",
            "create_directory", "path_info",
        }
        assert ctx.tools["path_info"]["auto_approved"] is True
        assert ctx.tools["delete_path"]["auto_approved"] is False
        for name, tool in ctx.tools.items():
            assert tool["parameters"]["type"] == "object"
            assert callable(tool["formatArguments"])
            assert callable(tool["generatePreview"])
            assert tool["description"]

    def test_preview_delete_reports_tree(self, workdir):
        (workdir / "d").mkdir()
        _write(workdir / "d" / "f.txt")
        preview = af._preview_delete({"path": "d", "recursive": True})
        assert preview["can_approve"] is True
        assert "1 entries" in preview["content"]

    def test_preview_move(self):
        preview = af._preview_move(
            {"source": "a", "destination": "b", "overwrite": True}
        )
        assert "a" in preview["content"]
        assert "Overwrite destination: yes" in preview["content"]

    def test_real_plugin_system_registers_tools(self, monkeypatch):
        from aicoder.core.plugin_system import PluginSystem

        monkeypatch.setenv(af.ENV_FLAG, "1")
        manager = PluginSystem()
        manager._load_single_plugin(af.__file__, "alt_filetools")
        assert {
            "move_path", "copy_path", "delete_path",
            "create_directory", "path_info",
        } <= set(manager.tools)
        assert manager.tools["path_info"]["auto_approved"] is True

    def test_real_plugin_system_skipped_when_disabled(self, monkeypatch):
        from aicoder.core.plugin_system import PluginSystem

        monkeypatch.delenv(af.ENV_FLAG, raising=False)
        manager = PluginSystem()
        manager._load_single_plugin(af.__file__, "alt_filetools")
        assert manager.tools == {}
