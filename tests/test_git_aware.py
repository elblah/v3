"""
Tests for the git_aware plugin's subprocess hardening.
"""

import subprocess

import pytest

from aicoder.plugins import git_aware


def _completed(returncode=0, stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_spawn_git_wraps_with_coreutils_timeout(monkeypatch):
    """timeout -k 1 N must wrap the whole git argv (kills the process group)."""
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _completed()

    monkeypatch.setattr(git_aware, "safe_subprocess_run", fake_run)

    result = git_aware._spawn_git(["status", "--porcelain"], timeout=2)

    assert result is not None
    assert captured["argv"][:4] == ["timeout", "-k", "1", "2"]
    assert captured["argv"][4] == "git"
    # python-side backstop fires later than the coreutils kill
    assert captured["kwargs"]["timeout"] == 4


def test_spawn_git_timeout_exit_codes_return_none(monkeypatch):
    """SIGTERM (124) and SIGKILL (137) exits mean 'no answer', not 'clean'."""
    for rc in (124, 137):
        monkeypatch.setattr(
            git_aware,
            "safe_subprocess_run",
            lambda argv, _rc=rc, **kwargs: _completed(returncode=_rc),
        )
        assert git_aware._spawn_git(["status", "--porcelain"], timeout=2) is None


def test_spawn_git_hardens_diff_against_repo_config(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _completed()

    monkeypatch.setattr(git_aware, "safe_subprocess_run", fake_run)

    git_aware._spawn_git(["diff", "--cached"], timeout=5)

    argv = captured["argv"]
    assert "core.fsmonitor=false" in argv
    assert "core.pager=cat" in argv
    assert "gc.auto=0" in argv
    assert "--no-ext-diff" in argv
    assert "--no-textconv" in argv
    # the subcommand itself stays right after the diff flags
    assert argv.index("--no-textconv") + 1 == argv.index("--cached")


def test_spawn_git_missing_binary_returns_none(monkeypatch):
    def boom(argv, **kwargs):
        raise FileNotFoundError("timeout")

    monkeypatch.setattr(git_aware, "safe_subprocess_run", boom)
    assert git_aware._spawn_git(["status"], timeout=2) is None


def test_spawn_git_python_timeout_returns_none(monkeypatch):
    def boom(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(git_aware, "safe_subprocess_run", boom)
    assert git_aware._spawn_git(["status"], timeout=2) is None
