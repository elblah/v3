#!/usr/bin/env python
"""Debug plugin loading with detailed tracing"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aicoder.core.plugin_system import PluginSystem
from aicoder.core.input_handler import InputHandler

os.chdir(Path(__file__).parent.parent)

# Create input handler
input_handler = InputHandler()

# Create mock app
class MockApp:
    def __init__(self, ih):
        self.input_handler = ih

mock_app = MockApp(input_handler)

# Create plugin system
plugin_system = PluginSystem(plugins_dir=".aicoder/plugins")
plugin_system.set_app(mock_app)

# Patch PluginContext.register_completer to see if it's called
original_register = plugin_system.context.register_completer

def traced_register(completer):
    print(f"\n[TRACE] PluginContext.register_completer() called!")
    print(f"  Completer function: {completer}")
    print(f"  plugin_system._app: {plugin_system._app}")
    print(f"  plugin_system._app.input_handler: {plugin_system._app.input_handler if plugin_system._app else None}")
    result = original_register(completer)
    print(f"  After registration, completers: {len(input_handler.completers)}")
    return result

plugin_system.context.register_completer = traced_register

# Patch PluginSystem._register_completer to see internal logic
original_internal = plugin_system._register_completer

def traced_internal(completer):
    print(f"\n[TRACE] PluginSystem._register_completer() called!")
    print(f"  Checking: self._app and self._app.input_handler")
    print(f"  self._app: {plugin_system._app}")
    print(f"  self._app.input_handler: {plugin_system._app.input_handler if plugin_system._app else None}")

    if plugin_system._app and plugin_system._app.input_handler:
        print(f"  Condition TRUE - will register")
        result = plugin_system._app.input_handler.register_completer(completer)
        print(f"  After register_completer: {len(input_handler.completers)} completers")
    else:
        print(f"  Condition FALSE - will NOT register")
        result = None

    return result

plugin_system._register_completer = traced_internal

# Load plugins
print("=" * 70)
print("Loading plugins...")
print("=" * 70)
plugin_system.load_plugins()

print("\n" + "=" * 70)
print("Final Results:")
print("=" * 70)
print(f"Hooks: {list(plugin_system.hooks.keys())}")
print(f"Commands: {list(plugin_system.commands.keys())}")
print(f"Completers registered: {len(input_handler.completers)}")
