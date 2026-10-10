"""Test privacy plugin: status, clear, clear-all, hook contributions, /new prompt"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from aicoder.plugins import privacy


class FakePluginSystem:
    """Records call_hooks invocations; returns canned contributions per event"""

    def __init__(self, contributions=None):
        self.calls = []
        self.contributions = contributions or {}

    def call_hooks(self, event, *args, **kwargs):
        self.calls.append((event, args))
        return self.contributions.get(event)


class FakeApp:
    def __init__(self, contributions=None):
        self.plugin_system = FakePluginSystem(contributions)
        self.stats = MagicMock()
        self.message_history = MagicMock()


class FakeCtx:
    def __init__(self, contributions=None):
        self.app = FakeApp(contributions)
        self.commands = {}

    def register_command(self, name, handler, description=None):
        self.commands[name] = handler


class AnswerQueue:
    """Stand-in for prompt_choice: pops queued answers, default "no" when empty"""

    def __init__(self):
        self.pending = []
        self.prompts = []

    def push(self, *values):
        self.pending.extend(values)

    def __call__(self, prompt, history):
        self.prompts.append(prompt)
        return self.pending.pop(0) if self.pending else ""


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolate cwd and HOME so registry paths resolve inside tmp_path"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def answers(monkeypatch):
    q = AnswerQueue()
    monkeypatch.setattr(privacy, "prompt_choice", q)
    return q


def make_handler(contributions=None):
    ctx = FakeCtx(contributions)
    privacy.create_plugin(ctx)
    return ctx, ctx.commands["/privacy"]


def test_status_lists_registry(env):
    (env / ".aicoder").mkdir()
    (env / ".aicoder" / "history").write_text("a" * 100)
    _ctx, handler = make_handler()

    out = handler("")
    assert ".aicoder/history" in out
    assert "[x]" in out
    assert ".aicoder/memory" in out
    assert f"1/{len(privacy.REGISTRY)} present" in out


def test_unknown_arg_shows_usage(env):
    _ctx, handler = make_handler()
    out = handler("frobnicate")
    assert "Unknown argument: frobnicate" in out
    assert "/privacy clear-all" in out


def test_clear_all_deletes_registry_and_contributions(env, answers, capsys):
    root = env / ".aicoder"
    (root / "memory").mkdir(parents=True)
    (root / "memory" / "index.md").write_text("notes")
    (root / "current-session.jsonl").write_text("[]")
    (root / "history").write_text("[]")
    (root / "stats.log").write_text("stats")  # must survive the wipe

    extra = env / "extra"
    extra.mkdir()
    (extra / "dump.json").write_text("{}")
    (extra / "notes.txt").write_text("notes")

    contributions = {
        "on_privacy_clear": [
            {"path": "extra/dump.json", "description": "captured dumps"},
            "extra/notes.txt",
            {"path": "extra/missing.bin", "description": "already gone"},
        ]
    }
    ctx, handler = make_handler(contributions)
    answers.push("n")  # answer to the trailing /new prompt

    result = handler("clear-all")
    captured = capsys.readouterr().out

    assert result == ""
    assert not (root / "memory").exists()
    assert not (root / "current-session.jsonl").exists()
    assert not (root / "history").exists()
    assert (root / "stats.log").exists()  # stats logs are never cleared
    assert not (extra / "dump.json").exists()
    assert not (extra / "notes.txt").exists()
    assert extra.exists()  # contributed dir itself untouched
    assert "captured dumps" in captured
    assert "deleted 5, kept 0, failed 0" in captured
    assert ("on_privacy_clear", ("clear-all",)) in ctx.app.plugin_system.calls
    assert len(answers.prompts) == 1  # only the /new prompt, no per-item prompts


def test_clear_prompts_per_item(env, answers, capsys):
    root = env / ".aicoder"
    root.mkdir()
    (root / "history").write_text("[]")
    (root / "errors.log").write_text("trace")

    _ctx, handler = make_handler()
    answers.push("y", "")  # delete history; empty answer keeps errors.log

    result = handler("clear")
    captured = capsys.readouterr().out

    assert result == ""
    assert not (root / "history").exists()
    assert (root / "errors.log").exists()
    assert len(answers.prompts) == 2  # one prompt per existing artifact
    assert "kept" in captured


def test_normalize_contributions_rejects_junk(env):
    rows = privacy._normalize_contributions([
        None,
        "",
        "/",
        {"path": "", "description": "empty path"},
        {"description": "no path key"},
        42,
        "extra/x",
        {"path": "extra/y", "description": "d"},
        ["extra/z"],
    ])
    paths = [p for p, _ in rows]

    assert len(paths) == 3
    assert all(p != os.sep for p in paths)
    assert os.path.abspath("extra/x") in paths
    assert os.path.abspath("extra/y") in paths
    assert os.path.abspath("extra/z") in paths
    assert dict(rows)[os.path.abspath("extra/y")] == "d"


def test_normalize_contributions_handles_none():
    assert privacy._normalize_contributions(None) == []


def test_merge_entries_dedupe():
    merged = privacy._merge_entries([("/a", "first"), ("/a", "second"), ("/b", "")])
    assert merged == [
        {"path": "/a", "description": "first"},
        {"path": "/b", "description": ""},
    ]


def test_session_reset_prompt_yes(env, answers):
    root = env / ".aicoder"
    root.mkdir()
    session = root / "current-session.jsonl"
    session.write_text("[]")

    ctx, handler = make_handler()
    answers.push("y", "y")  # clear item; then accept the /new reset

    handler("clear")

    assert not session.exists()
    assert ("on_session_change", ("new",)) in ctx.app.plugin_system.calls
    assert ctx.app.stats.reset.called
    assert ctx.app.message_history.clear.called


def test_session_reset_prompt_no(env, answers):
    root = env / ".aicoder"
    root.mkdir()
    session = root / "current-session.jsonl"
    session.write_text("[]")

    ctx, handler = make_handler()
    answers.push("y", "n")  # clear item; decline the /new reset

    handler("clear")

    assert not session.exists()
    assert ("on_session_change", ("new",)) not in ctx.app.plugin_system.calls
    assert not ctx.app.stats.reset.called
    assert not ctx.app.message_history.clear.called
