"""Test tmux plugin _restore_session mode logic (rs / rs n / rs full)"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from aicoder.plugins import tmux


def _fake_run(stdout_text):
    """Return a subprocess.run replacement returning fake capture output."""
    def fake_run(cmd, **kwargs):
        assert cmd[0] == "tmux" and cmd[1] == "capture-pane"
        return types.SimpleNamespace(
            returncode=0, stdout=stdout_text, stderr=""
        )
    return fake_run


def _mkpane(marker_count, junk_between=3):
    """Build pane text with marker_count markers at known line offsets."""
    lines = [f"top-junk-{j}" for j in range(junk_between)]
    marker = f"{tmux.MARKER_PREFIX} {tmux.MARKER_TEXT} SESSION"
    for i in range(marker_count):
        lines.extend(f"junk-before-{i}-{j}" for j in range(junk_between))
        lines.append(f"{marker} {i}")
    lines.append("final-content-line")
    return "\n".join(lines) + "\n"


class FakeApp:
    def __init__(self):
        self.prompts = []

    def set_next_prompt(self, content):
        self.prompts.append(content)


class FakeCtx:
    def __init__(self):
        self.app = FakeApp()


def _run(mode, pane_text):
    """Run _restore_session with mocked capture/editor; return (ctx, editor_calls)."""
    ctx = FakeCtx()
    editor_mock = MagicMock(return_value=True)
    with patch.object(tmux.subprocess, "run", _fake_run(pane_text)), \
         patch("aicoder.utils.tmux_edit_utils.tmux_open_editor", editor_mock):
        tmux._restore_session(ctx, mode)
    return ctx, editor_mock


def _run_full(pane_text):
    """mode='full' path: no editor; capture injected prompt and editor calls."""
    ctx = FakeCtx()
    editor_mock = MagicMock(return_value=True)
    with patch.object(tmux.subprocess, "run", _fake_run(pane_text)):
        tmux._restore_session(ctx, "full")
    return ctx, editor_mock


def _marker_line(idx):
    return f"{tmux.MARKER_PREFIX} {tmux.MARKER_TEXT} SESSION {idx}"


def test_rs_n_uses_nth_previous_marker():
    """5 markers, rs 3 → content starts at markers[-4] (2 sessions before current)."""
    pane = _mkpane(5)
    ctx, _ = _run(3, pane)
    assert ctx.app.prompts, "expected injected prompt"
    assert ctx.app.prompts[0].startswith(_marker_line(1)), \
        f"expected start at marker 1, got: {ctx.app.prompts[0][:60]!r}"
    # end of capture: content was trimmed from marker 1 onward
    assert ctx.app.prompts[0].endswith("final-content-line")


def test_rs_n_falls_back_to_earliest_marker():
    """2 markers, rs 5 → not enough markers; content starts at earliest marker."""
    pane = _mkpane(2)
    ctx, _ = _run(5, pane)
    assert ctx.app.prompts[0].startswith(_marker_line(0))


def test_rs_n_no_markers_uses_full_scrollback():
    """0 markers, rs 2 → full scrollback content."""
    pane = _mkpane(0)
    ctx, _ = _run(2, pane)
    assert ctx.app.prompts[0].startswith("top-junk-0")
    assert ctx.app.prompts[0].endswith("final-content-line")


def test_rs_default_previous_session():
    """3 markers, rs (None) → content starts at second-to-last marker."""
    pane = _mkpane(3)
    ctx, _ = _run(None, pane)
    assert ctx.app.prompts[0].startswith(_marker_line(1))


def test_rs_default_single_marker_current_session():
    """1 marker, rs (None) → content starts at the single marker."""
    pane = _mkpane(1)
    ctx, _ = _run(None, pane)
    assert ctx.app.prompts[0].startswith(_marker_line(0))


def test_rs_default_no_markers_full():
    """0 markers, rs (None) → full scrollback."""
    pane = _mkpane(0)
    ctx, _ = _run(None, pane)
    assert ctx.app.prompts[0].startswith("top-junk-0")


def test_rs_full_raw_no_editor():
    """rs full → raw pane content injected, editor never opened."""
    pane = _mkpane(2)
    ctx, editor_mock = _run_full(pane)
    assert ctx.app.prompts, "expected injected prompt"
    assert ctx.app.prompts[0] == pane.strip()
    editor_mock.assert_not_called()


def test_rs_full_ignores_markers_in_output():
    """rs full keeps marker lines inside content (no trimming)."""
    pane = _mkpane(2)
    ctx, _ = _run_full(pane)
    assert _marker_line(0) in ctx.app.prompts[0]


def test_rs_n_one_marker_available():
    """1 marker, rs 2 → falls back to that single marker."""
    pane = _mkpane(1)
    ctx, _ = _run(2, pane)
    assert ctx.app.prompts[0].startswith(_marker_line(0))


def test_editor_used_for_int_and_default_modes():
    """rs n and rs default go through the editor; rs full does not."""
    pane = _mkpane(3)
    _, editor_rs = _run(2, pane)
    editor_rs.assert_called_once()
    _, editor_default = _run(None, pane)
    editor_default.assert_called_once()
    _, editor_full = _run_full(pane)
    editor_full.assert_not_called()
