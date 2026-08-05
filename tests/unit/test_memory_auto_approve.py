"""Test memory plugin auto-approval of write_file/edit_file on memory paths."""

import importlib
import os
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent.parent


class FakeCtx:
    def __init__(self):
        self.app = None
        self.hooks = {}
        self.commands = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_command(self, name, fn, description=""):
        self.commands[name] = fn


@pytest.fixture
def hook(monkeypatch):
    """Load memory plugin with AICODER_MEMORY_AUTO_APPROVE=1, return approval hook."""
    monkeypatch.setenv("AICODER_MEMORY_AUTO_APPROVE", "1")
    monkeypatch.setenv("AICODER_MEMORY_PREVIEW_HIDE", "0")
    module = importlib.import_module("aicoder.plugins.memory")
    importlib.reload(module)
    ctx = FakeCtx()
    module.create_plugin(ctx)
    return ctx.hooks["before_approval_prompt"]


@pytest.fixture
def preview_hook(monkeypatch):
    """Load memory plugin, return the on_tool_preview hook."""
    monkeypatch.setenv("AICODER_MEMORY_AUTO_APPROVE", "1")
    monkeypatch.setenv("AICODER_MEMORY_PREVIEW_HIDE", "0")
    module = importlib.import_module("aicoder.plugins.memory")
    importlib.reload(module)
    ctx = FakeCtx()
    module.create_plugin(ctx)
    return ctx.hooks["on_tool_preview"]


def test_approves_write_file_in_memory_dir(hook):
    assert hook("write_file", {"path": ".aicoder/memory/index.md"}) is True


def test_approves_edit_file_absolute_memory_path(hook):
    p = str(REPO / ".aicoder/memory/notes.md")
    assert hook("edit_file", {"path": p}) is True


def test_approves_subdirectory_of_memory_dir(hook):
    assert hook("write_file", {"path": ".aicoder/memory/topics/api.md"}) is True


def test_does_not_approve_outside_memory_dir(hook):
    assert hook("write_file", {"path": "main.py"}) is None
    assert hook("edit_file", {"path": ".aicoder/other.md"}) is None
    assert hook("write_file", {"path": "memory.md"}) is None


def test_does_not_approve_non_write_tools(hook):
    assert hook("run_shell_command", {"command": "rm -rf .aicoder/memory"}) is None
    assert hook("read_file", {"path": ".aicoder/memory/index.md"}) is None
    assert hook("list_directory", {"path": ".aicoder/memory"}) is None


def test_missing_path_or_args(hook):
    assert hook("write_file", {}) is None
    assert hook("edit_file", None) is None
    assert hook("write_file", {"content": "no path"}) is None


def test_disabled_via_env(monkeypatch):
    monkeypatch.setenv("AICODER_MEMORY_AUTO_APPROVE", "0")
    monkeypatch.setenv("AICODER_MEMORY_PREVIEW_HIDE", "0")
    module = importlib.import_module("aicoder.plugins.memory")
    importlib.reload(module)
    ctx = FakeCtx()
    module.create_plugin(ctx)
    hook = ctx.hooks["before_approval_prompt"]
    assert hook("write_file", {"path": ".aicoder/memory/index.md"}) is None


class TestMemoryPreviewHook:
    def test_summary_dict_for_memory_path(self, preview_hook):
        result = preview_hook(
            "write_file",
            {"path": ".aicoder/memory/index.md"},
            {"content": "diff...", "can_approve": True},
        )
        assert isinstance(result, dict)
        assert result["can_approve"] is True
        assert "index.md" in result["content"]
        assert "diff hidden" in result["content"]

    def test_absolute_memory_path(self, preview_hook):
        p = str(REPO / ".aicoder/memory/notes.md")
        result = preview_hook("edit_file", {"path": p}, {"content": "diff", "can_approve": True})
        assert isinstance(result, dict)
        assert "notes.md" in result["content"]

    def test_none_outside_memory_dir(self, preview_hook):
        result = preview_hook("write_file", {"path": "main.py"}, {"content": "diff", "can_approve": True})
        assert result is None

    def test_none_for_non_write_tools(self, preview_hook):
        assert preview_hook("run_shell_command", {"command": "ls"}, {}) is None
        assert preview_hook("read_file", {"path": ".aicoder/memory/index.md"}, {}) is None

    def test_none_missing_args(self, preview_hook):
        assert preview_hook("write_file", {}, {"content": "x", "can_approve": True}) is None
        assert preview_hook("write_file", None, {}) is None

    def test_hidden_via_env(self, monkeypatch):
        monkeypatch.setenv("AICODER_MEMORY_PREVIEW_HIDE", "1")
        module = importlib.import_module("aicoder.plugins.memory")
        importlib.reload(module)
        ctx = FakeCtx()
        module.create_plugin(ctx)
        hook = ctx.hooks["on_tool_preview"]
        assert hook("write_file", {"path": ".aicoder/memory/index.md"}, {"content": "diff", "can_approve": True}) is False
