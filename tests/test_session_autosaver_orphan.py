import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aicoder.core.message_history import MessageHistory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Module name has a dash — load via importlib
_spec = importlib.util.spec_from_file_location(
    "session_autosaver", os.path.join(ROOT, "aicoder", "plugins", "session-autosaver.py")
)
autosaver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(autosaver)


class FakeStats:
    current_prompt_size = 0

    def set_current_prompt_size(self, tokens, cached):
        self.current_prompt_size = tokens


class FakeApp:
    def __init__(self, msgs):
        self.stats = FakeStats()
        self.message_history = MessageHistory(self.stats)
        self.message_history.set_messages(msgs)


class FakeCtx:
    def __init__(self, app):
        self.app = app
        self.hooks = {}
        self.commands = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_command(self, name, fn, description=None):
        self.commands[name] = fn


SYSTEM_MSG = {"role": "system", "content": "sys"}
PARENT_MSG = {
    "role": "assistant",
    "tool_calls": [{"id": "call_1", "name": "fake", "arguments": "{}"}],
}
RESULT_MSG = {"role": "tool", "tool_call_id": "call_1", "content": "ok"}
ORPHAN_MSG = {"role": "tool", "tool_call_id": "call_ghost", "content": "straggler"}


def write_jsonl(path, msgs):
    with open(path, "w") as f:
        f.writelines(json.dumps(m) + "\n" for m in msgs)


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class TestLoaderOrphanCleanup(unittest.TestCase):
    def setUp(self):
        self._old_session = os.environ.get("SESSION_FILE")
        self._tmpdir = tempfile.mkdtemp(prefix="autosave_test_")
        self.session_file = os.path.join(self._tmpdir, "session.jsonl")
        os.environ["SESSION_FILE"] = self.session_file
        # Ensure no confirm prompt in CI (stdin is not a tty anyway)
        os.environ.pop("SESSION_FILE_CONFIRM_AUTOLOAD", None)

    def tearDown(self):
        if self._old_session is None:
            os.environ.pop("SESSION_FILE", None)
        else:
            os.environ["SESSION_FILE"] = self._old_session
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_plugin(self):
        app = FakeApp([SYSTEM_MSG])
        ctx = FakeCtx(app)
        plugin = autosaver.create_plugin(ctx)
        return app, ctx, plugin

    def test_orphan_dropped_on_load_and_persisted(self):
        write_jsonl(self.session_file, [PARENT_MSG, RESULT_MSG, ORPHAN_MSG])

        app, ctx, plugin = self._make_plugin()
        self.assertIsNotNone(plugin)

        ctx.hooks["after_session_initialized"]([])

        # Orphan removed from memory, valid result kept
        msgs = app.message_history.messages
        self.assertEqual(len(msgs), 3)  # system + parent + result
        self.assertFalse(any(
            m.get("tool_call_id") == "call_ghost" for m in msgs
        ))
        self.assertTrue(any(
            m.get("tool_call_id") == "call_1" for m in msgs
        ))

        # Cleaned state persisted — reload is safe
        file_msgs = read_jsonl(self.session_file)
        self.assertFalse(any(
            m.get("tool_call_id") == "call_ghost" for m in file_msgs
        ))
        self.assertTrue(any(
            m.get("tool_call_id") == "call_1" for m in file_msgs
        ))
        plugin["cleanup"]()

    def test_clean_file_untouched(self):
        write_jsonl(self.session_file, [PARENT_MSG, RESULT_MSG])

        app, ctx, plugin = self._make_plugin()
        ctx.hooks["after_session_initialized"]([])

        self.assertEqual(len(app.message_history.messages), 3)  # system + parent + result
        file_msgs = read_jsonl(self.session_file)
        self.assertEqual(len(file_msgs), 2)
        plugin["cleanup"]()

    def test_disabled_without_session_file(self):
        os.environ.pop("SESSION_FILE", None)
        app = FakeApp([SYSTEM_MSG])
        ctx = FakeCtx(app)
        self.assertIsNone(autosaver.create_plugin(ctx))

    def test_lock_sidecar_created_and_acquired(self):
        app, ctx, plugin = self._make_plugin()
        self.assertIsNotNone(plugin)
        self.assertTrue(os.path.exists(self.session_file + ".lock"))
        plugin["cleanup"]()

    def test_lock_contention_exits(self):
        import fcntl

        lock_path = self.session_file + ".lock"
        with open(lock_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            app = FakeApp([SYSTEM_MSG])
            ctx = FakeCtx(app)
            with self.assertRaises(SystemExit):
                autosaver.create_plugin(ctx)
            fcntl.flock(f, fcntl.LOCK_UN)


if __name__ == "__main__":
    unittest.main()
