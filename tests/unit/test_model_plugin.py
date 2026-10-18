"""
Unit tests for the bundled /model plugin.
"""

import types
from unittest.mock import patch

from aicoder.plugins import model


class FakeCtx:
    def __init__(self, app=None):
        self.app = app
        self.registered = {}

    def register_command(self, name, handler, description=None):
        self.registered[name] = (handler, description)


def _ctx_with_plugin_system(commands):
    ps = types.SimpleNamespace(commands=commands)
    app = types.SimpleNamespace(plugin_system=ps)
    return FakeCtx(app=app)


class TestModelPlugin:
    def test_prints_model_name(self):
        ctx = _ctx_with_plugin_system({})
        model.create_plugin(ctx)
        handler, _ = ctx.registered["model"]
        with patch.object(model.Config, "model", return_value="deepseek/deepseek-v4.1-flash"):
            assert handler("") == "model: deepseek/deepseek-v4.1-flash"

    def test_missing_model_falls_back_to_unknown(self):
        ctx = _ctx_with_plugin_system({})
        model.create_plugin(ctx)
        handler, _ = ctx.registered["model"]
        with patch.object(model.Config, "model", return_value=""):
            assert handler("") == "model: unknown"

    def test_skips_registration_when_higher_priority_plugin_owns_it(self):
        ctx = _ctx_with_plugin_system({"model": {"fn": lambda args: None}})
        model.create_plugin(ctx)
        assert ctx.registered == {}

    def test_registers_without_app_reference(self):
        ctx = FakeCtx(app=None)
        model.create_plugin(ctx)
        assert "model" in ctx.registered
