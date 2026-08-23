"""
Tests for internal skills: virtual files served via read_file at
/internal/<skill>/<file>, registered lazily via on_internal_skills hooks.
"""

import os
from types import SimpleNamespace

import pytest

import aicoder.tools.internal.read_file as rf
from aicoder.core.config import Config
from aicoder.plugins.skills import (
    INTERNAL_PREFIX,
    SkillsManager,
    _merge_internal_results,
    create_plugin as create_skills_plugin,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeReadFileHooks:
    """Fake plugin system whose on_read_file hook returns canned results."""

    def __init__(self, results):
        self._results = results

    def call_hooks(self, event, *args, **kwargs):
        if event == "on_read_file":
            return list(self._results)
        return None


class FakeInternalHooks:
    """Fake plugin system for skills.py: canned on_internal_skills results."""

    def __init__(self, results):
        self._results = results

    def call_hooks(self, event, *args, **kwargs):
        if event == "on_internal_skills":
            return list(self._results)
        return None


class StubCtx:
    """Minimal plugin context capturing registered hooks/commands."""

    def __init__(self, plugin_system=None):
        self.app = SimpleNamespace(plugin_system=plugin_system)
        self.hooks = {}
        self.commands = {}

    def register_hook(self, name, fn):
        self.hooks.setdefault(name, []).append(fn)

    def register_command(self, name, handler, description=None):
        self.commands[name] = handler


@pytest.fixture
def read_file_plugin():
    """Install a fake plugin system into read_file, restore after."""
    old = rf._plugin_system
    yield
    rf._plugin_system = old


@pytest.fixture
def clear_read_tracker():
    from aicoder.core.file_access_tracker import FileAccessTracker
    FileAccessTracker.clear_state()
    yield
    FileAccessTracker.clear_state()


# ---------------------------------------------------------------------------
# read_file intercept
# ---------------------------------------------------------------------------

def test_virtual_content_served(read_file_plugin):
    rf.set_plugin_system(FakeReadFileHooks([None, "hello virtual"]))
    result = rf.execute({"path": "/internal/foo/SKILL.md"})
    assert result["detailed"]
    assert "File: /internal/foo/SKILL.md" in result["detailed"]
    assert "hello virtual" in result["detailed"]
    # first hook returned None (observing) -> second hook's str wins


def test_virtual_pagination(read_file_plugin):
    content = "\n".join(f"line {i}" for i in range(1, 11))  # 10 lines
    rf.set_plugin_system(FakeReadFileHooks([content]))
    result = rf.execute({"path": "/internal/demo/notes.md", "offset": 2, "limit": 3})
    assert "File: /internal/demo/notes.md" in result["detailed"]
    assert "Total lines: 10" in result["detailed"]
    assert "Showing: lines 3-5" in result["detailed"]
    assert "line 3" in result["detailed"] and "line 4" in result["detailed"]
    assert "line 6" not in result["detailed"]


def test_virtual_not_tracked(read_file_plugin, clear_read_tracker):
    from aicoder.core.file_access_tracker import FileAccessTracker
    rf.set_plugin_system(FakeReadFileHooks(["virtual content"]))
    result = rf.execute({"path": "/internal/foo/SKILL.md"})
    assert FileAccessTracker.get_all_read_files() == set()


def test_real_file_unaffected(read_file_plugin, clear_read_tracker):
    from aicoder.core.file_access_tracker import FileAccessTracker
    rf.set_plugin_system(FakeReadFileHooks([None]))  # hook declines
    result = rf.execute({"path": "tests/test_internal_skills.py"})
    assert "def test_real_file_unaffected" in result["detailed"]
    assert FileAccessTracker.get_all_read_files() == {"tests/test_internal_skills.py"}


def test_sandbox_still_blocks_outside(read_file_plugin):
    if Config.sandbox_disabled():
        pytest.skip("sandbox disabled (MINI_SANDBOX=0)")
    rf.set_plugin_system(FakeReadFileHooks([None]))
    with pytest.raises(Exception):
        rf.execute({"path": "/etc/hostname"})


def test_no_plugin_system_normal_read(read_file_plugin, clear_read_tracker):
    from aicoder.core.file_access_tracker import FileAccessTracker
    rf.set_plugin_system(None)
    result = rf.execute({"path": "tests/test_internal_skills.py", "limit": 2})
    assert "Total lines:" in result["detailed"]
    assert FileAccessTracker.get_all_read_files() == {"tests/test_internal_skills.py"}


# ---------------------------------------------------------------------------
# skills.py unit tests
# ---------------------------------------------------------------------------

def test_merge_first_wins_and_skips_garbage():
    a = {"description": "A"}
    a2 = {"description": "A2"}
    b = {"description": "B"}
    merged = _merge_internal_results([None, {"a": a}, "garbage", 42, {"a": a2, "b": b}, {"c": "not-a-dict"}])
    assert merged == {"a": a, "b": b}  # first wins, non-dicts skipped


def test_merge_empty():
    assert _merge_internal_results(None) == {}
    assert _merge_internal_results([]) == {}
    assert _merge_internal_results(["garbage"]) == {}


def test_generate_skills_text_internal_lines():
    manager = SkillsManager()  # fresh, no discover -> no real skills
    out = manager.generate_skills_text(
        internal_skills={"demo": {"description": "Demo skill", "files": {"SKILL.md": "x"}}}
    )
    assert "- demo (/internal/demo/SKILL.md): Demo skill" in out


def test_generate_skills_text_empty_guard():
    manager = SkillsManager()
    assert manager.generate_skills_text() == ""
    assert manager.generate_skills_text(internal_skills={}) == ""
    assert manager.generate_skills_text(internal_skills=None) == ""


def test_handle_internal_read_via_hooks():
    skill = {"description": "Demo", "files": {"SKILL.md": "doc content", "extra.md": "extra"}}
    ctx = StubCtx(plugin_system=FakeInternalHooks([{"demo": skill}]))
    create_skills_plugin(ctx)

    handle = ctx.hooks["on_read_file"][0]
    assert handle("/internal/demo/SKILL.md") == "doc content"
    assert handle("/internal/demo/extra.md") == "extra"
    assert handle("/internal/demo/") == "doc content"  # default SKILL.md
    assert handle("/internal/demo") == "doc content"
    assert handle("/internal/unknown/SKILL.md") is None
    assert handle("/internal//SKILL.md") is None  # empty skill name
    assert handle("/internal/demo/missing.md") is None
    assert handle("/etc/hostname") is None  # non-prefix falls through
    assert handle("internal/demo/SKILL.md") is None


def test_prompt_append_uses_internal_registry():
    skill = {"description": "Demo", "files": {"SKILL.md": "x"}}
    ctx = StubCtx(plugin_system=FakeInternalHooks([{"demo": skill}]))
    create_skills_plugin(ctx)
    out = ctx.hooks["on_system_prompt_append"][0]()
    assert "- demo (/internal/demo/SKILL.md): Demo" in out


def test_internal_registry_requires_plugin_system():
    ctx = StubCtx(plugin_system=None)
    create_skills_plugin(ctx)
    out = ctx.hooks["on_system_prompt_append"][0]()
    assert "/internal/" not in out  # no app/plugin_system -> no internal lines, no crash


def test_sandbox_whitelist_hook_registered():
    ctx = StubCtx(plugin_system=None)
    create_skills_plugin(ctx)
    handlers = ctx.hooks.get("on_file_sandbox_whitelist")
    assert handlers, "skills plugin must register on_file_sandbox_whitelist"

    dirs = handlers[0]()
    assert isinstance(dirs, list)
    assert any(d.endswith("/skills") for d in dirs)
    assert any(d.endswith("/skills-extra") for d in dirs)
    assert all(d.startswith("/") for d in dirs)


# ---------------------------------------------------------------------------
# Integration with real PluginSystem (lazy registration order proof)
# ---------------------------------------------------------------------------

PROVIDER_PLUGIN = '''
def create_plugin(ctx):
    def handler():
        return {"demo": {"description": "Demo skill",
                         "files": {"SKILL.md": "demo line1\\ndemo line2"}}}
    ctx.register_hook("on_internal_skills", handler)
    return None
'''


def test_plugin_system_lazy_order(tmp_path, read_file_plugin):
    from aicoder.core.plugin_system import PluginSystem

    provider_dir = tmp_path / "provider"
    provider_dir.mkdir()
    (provider_dir / "provider_plugin.py").write_text(PROVIDER_PLUGIN)
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    ps = PluginSystem(plugins_dir=str(provider_dir), global_plugins_dir=str(empty_dir))
    ps.set_app(SimpleNamespace(plugin_system=ps))  # production: aicoder.py:127
    # skills plugin registers FIRST, before provider loads. If the internal
    # registry were eager, it would see nothing. Lazy query must find the
    # provider's skill once it loads.
    create_skills_plugin(ps.context)
    ps._load_plugins_from_dir(str(provider_dir), "local")

    results = ps.call_hooks("on_read_file", "/internal/demo/SKILL.md")
    assert results == ["demo line1\ndemo line2"]

    # Full read_file path through the real plugin system.
    rf.set_plugin_system(ps)
    result = rf.execute({"path": "/internal/demo/SKILL.md"})
    assert "demo line1" in result["detailed"]


# ---------------------------------------------------------------------------
# Bundled plugin: tools_compact dogfoods the internal-skill mechanism
# ---------------------------------------------------------------------------

def test_tools_compact_registers_skill_when_enabled(monkeypatch):
    monkeypatch.setenv("TOOLS_COMPACT_ENABLED", "1")
    from aicoder.plugins import tools_compact

    ctx = StubCtx()
    tools_compact.create_plugin(ctx)
    assert "on_internal_skills" in ctx.hooks

    result = ctx.hooks["on_internal_skills"][0]()
    assert isinstance(result, dict)
    assert "tools-compact" in result
    skill = result["tools-compact"]
    assert "description" in skill
    files = skill["files"]
    assert "SKILL.md" in files
    skill_md = files["SKILL.md"]
    assert len(skill_md) > 200  # real teaching content, not a stub
    assert "COMPACT_SUMMARY:TOOLS" in skill_md
    assert "MANDATORY" in skill_md
    assert "reasoning" in skill_md  # tag must never go in reasoning
    assert "DELETED" in skill_md  # summary = only record of consumed loop


def test_tools_compact_registers_nothing_when_disabled(monkeypatch):
    monkeypatch.setenv("TOOLS_COMPACT_ENABLED", "0")
    from aicoder.plugins import tools_compact

    ctx = StubCtx()
    tools_compact.create_plugin(ctx)
    assert "on_internal_skills" not in ctx.hooks
