"""Tests for the file_guard plugin (on_file_access vetoes)."""

import os

import pytest

from aicoder.plugins import file_guard


class FakeContext:
    def __init__(self):
        self.hooks = {}
        self.commands = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_command(self, name, fn, description=""):
        self.commands[name] = fn


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AICODER_PROTECT_FILES", raising=False)
    monkeypatch.delenv("AICODER_FILE_GUARD", raising=False)
    ctx = FakeContext()
    file_guard.create_plugin(ctx)
    return ctx


def test_default_stats_logs_blocked(plugin, tmp_path):
    hook = plugin.hooks["on_file_access"]
    local = os.path.realpath(str(tmp_path / ".aicoder/stats.log"))
    assert "AI usage log" in hook(local, False, "read_file")
    assert "AI usage log" in hook(local, True, "write_file")
    central = os.path.realpath(
        os.path.expanduser("~/.aicoder/central_stats.log")
    )
    assert "AI usage log" in hook(central, False, "read_file")


def test_neighbour_files_stay_reachable(plugin, tmp_path):
    hook = plugin.hooks["on_file_access"]
    assert hook(str(tmp_path / ".aicoder/memory/index.md"), False, "read_file") is None
    # prefix must not match a longer name
    assert hook(os.path.realpath(str(tmp_path / ".aicoder/stats.log.bak")), False, "x") is None


def test_env_extra_paths_and_dirs(plugin, monkeypatch, tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    monkeypatch.setenv("AICODER_PROTECT_FILES", str(secrets))
    hook = plugin.hooks["on_file_access"]
    assert "AICODER_PROTECT_FILES" in hook(str(secrets / "key.pem"), False, "read_file")
    assert hook(str(tmp_path / "other.txt"), False, "read_file") is None


def test_env_glob_rule(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("AICODER_PROTECT_FILES", str(tmp_path / "*.env"))
    hook = plugin.hooks["on_file_access"]
    assert hook(str(tmp_path / "prod.env"), False, "read_file")
    assert hook(str(tmp_path / "prod.txt"), False, "read_file") is None


def test_tilde_and_relative_entries(plugin, monkeypatch):
    monkeypatch.setenv("AICODER_PROTECT_FILES", "docs/private" + os.pathsep + "~/.ssh")
    hook = plugin.hooks["on_file_access"]
    assert hook(os.path.realpath("docs/private/notes.md"), False, "read_file")
    assert hook(os.path.realpath(os.path.expanduser("~/.ssh/id_rsa")), False, "r")


def test_disable_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AICODER_FILE_GUARD", "0")
    ctx = FakeContext()
    file_guard.create_plugin(ctx)
    assert "on_file_access" not in ctx.hooks


def test_shell_command_rewritten(plugin):
    hook = plugin.hooks["on_before_run_shell_command"]
    rewritten = hook("cat .aicoder/stats.log")
    assert rewritten and "file_guard" in rewritten
    assert "cat" not in rewritten.split("blocked")[0]
    assert hook("ls -la") is None


def test_guard_command_lists_rules(plugin):
    handler = plugin.commands["/guard"]
    handler([])  # must not raise
