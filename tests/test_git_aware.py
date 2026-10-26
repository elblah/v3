"""
Tests for the git_aware plugin's subprocess hardening.
"""

import subprocess
import time

import pytest

from aicoder.core.config import Config
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


class _FakeCtx:
    """Minimal plugin context: captures hooks so we can call them directly."""

    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_command(self, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def _reset_dirty_cache():
    """Each test starts with a cold cache and no backoff."""
    git_aware._dirty_value = None
    git_aware._dirty_ok = False
    git_aware._dirty_ts = 0.0
    git_aware._dirty_skip_until = 0.0
    yield
    git_aware._dirty_value = None
    git_aware._dirty_ok = False
    git_aware._dirty_ts = 0.0
    git_aware._dirty_skip_until = 0.0


def _bar(monkeypatch, status_result, prime=True):
    """Load the plugin against a fake repo and return the bar segment."""
    monkeypatch.setattr(git_aware, "_is_git_repo", lambda: True)
    monkeypatch.setattr(git_aware, "_spawn_git", lambda *a, **kw: status_result)
    monkeypatch.setattr(git_aware, "_cached_git_branch", None)

    ctx = _FakeCtx()
    git_aware.create_plugin(ctx)
    hook = ctx.hooks["on_context_bar"]
    if prime:
        hook()  # first render queries git, caches the answer
    return hook


def test_first_render_does_not_wait_and_shows_unknown(monkeypatch):
    """Cold cache renders magenta 'Git?' before any git call is made."""
    calls = []
    monkeypatch.setattr(git_aware, "_is_git_repo", lambda: True)
    monkeypatch.setattr(git_aware, "_spawn_git", lambda *a, **kw: calls.append(a) or None)
    ctx = _FakeCtx()
    git_aware.create_plugin(ctx)
    # Simulate "no time to wait": backoff is armed, so no subprocess runs.
    git_aware._dirty_skip_until = time.monotonic() + 10
    assert ctx.hooks["on_context_bar"]() == f"{Config.colors['brightMagenta']}Git?"
    assert calls == []


def test_bar_clean_is_dim(monkeypatch):
    segment = _bar(monkeypatch, _completed(stdout=""))()
    assert segment == f"{Config.colors['dim']}Git"


def test_bar_dirty_is_bold_yellow(monkeypatch):
    segment = _bar(monkeypatch, _completed(stdout=" M a.py\n"))()
    assert segment == f"{Config.colors['yellow']}{Config.colors['bold']}Git"


def test_bar_timeout_is_magenta_unknown(monkeypatch):
    """Timed-out git must not render as clean."""
    segment = _bar(monkeypatch, None)()
    assert segment == f"{Config.colors['brightMagenta']}Git?"


def test_bar_failed_git_is_magenta_unknown(monkeypatch):
    segment = _bar(monkeypatch, _completed(returncode=128))()
    assert segment == f"{Config.colors['brightMagenta']}Git?"


def test_stall_arms_backoff_and_skips_next_render(monkeypatch):
    """After a timeout nothing else touches the disk for a while."""
    calls = []

    def fake_spawn(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(git_aware, "_is_git_repo", lambda: True)
    monkeypatch.setattr(git_aware, "_spawn_git", fake_spawn)
    ctx = _FakeCtx()
    git_aware.create_plugin(ctx)
    hook = ctx.hooks["on_context_bar"]

    hook()
    assert len(calls) == 1
    hook()  # within backoff window: no second subprocess
    hook()
    assert len(calls) == 1
    assert git_aware._dirty_skip_until > time.monotonic()


def test_stall_keeps_last_known_state(monkeypatch):
    """Known dirty + a later stall renders 'Git?' in the dirty colour."""
    results = [_completed(stdout=" M a.py\n"), None]

    def fake_spawn(*args, **kwargs):
        return results.pop(0) if results else None

    monkeypatch.setattr(git_aware, "_is_git_repo", lambda: True)
    monkeypatch.setattr(git_aware, "_spawn_git", fake_spawn)
    ctx = _FakeCtx()
    git_aware.create_plugin(ctx)
    hook = ctx.hooks["on_context_bar"]

    assert hook() == f"{Config.colors['yellow']}{Config.colors['bold']}Git"
    git_aware._dirty_ts = 0.0  # expire the cached answer
    segment = hook()
    assert segment == f"{Config.colors['yellow']}{Config.colors['bold']}Git?"


def test_answer_reused_within_ttl(monkeypatch):
    """The second bar render of a turn costs no subprocess."""
    calls = []

    def fake_spawn(*args, **kwargs):
        calls.append(args)
        return _completed(stdout="")

    monkeypatch.setattr(git_aware, "_is_git_repo", lambda: True)
    monkeypatch.setattr(git_aware, "_spawn_git", fake_spawn)
    ctx = _FakeCtx()
    git_aware.create_plugin(ctx)
    hook = ctx.hooks["on_context_bar"]

    hook()
    hook()
    assert len(calls) == 1


def test_status_allows_index_refresh(monkeypatch):
    """Dirty check lets git persist the stat cache (keeps warm runs cheap)."""
    import inspect

    src = inspect.getsource(git_aware._dirty_query)
    assert "optional_locks=True" in src
