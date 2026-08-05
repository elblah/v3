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
    module = importlib.import_module("aicoder.plugins.memory")
    importlib.reload(module)
    ctx = FakeCtx()
    module.create_plugin(ctx)
    return ctx.hooks["before_approval_prompt"]


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
    module = importlib.import_module("aicoder.plugins.memory")
    importlib.reload(module)
    ctx = FakeCtx()
    module.create_plugin(ctx)
    hook = ctx.hooks["before_approval_prompt"]
    assert hook("write_file", {"path": ".aicoder/memory/index.md"}) is None
