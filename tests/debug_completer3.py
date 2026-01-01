#!/usr/bin/env python
"""Debug completer registration - check internal method"""

import sys
import importlib.util
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aicoder.core.plugin_system import PluginSystem
from aicoder.core.input_handler import InputHandler

# Create input handler
input_handler = InputHandler()

# Create mock app
class MockApp:
    def __init__(self, ih):
        self.input_handler = ih

mock_app = MockApp(input_handler)

# Load plugin manually
plugin_system = PluginSystem()
plugin_system.set_app(mock_app)

# Patch _register_completer to see what happens
original_internal_register = plugin_system._register_completer

def traced_register(completer):
    print(f"\n_register_completer called!")
    print(f"  plugin_system._app: {plugin_system._app}")
    print(f"  plugin_system._app.input_handler: {plugin_system._app.input_handler if plugin_system._app else None}")
    print(f"  Condition (self._app and self._app.input_handler): {plugin_system._app is not None and (plugin_system._app.input_handler if plugin_system._app else None) is not None}")

    # Manually call registration
    if plugin_system._app and plugin_system._app.input_handler:
        print(f"  → Calling input_handler.register_completer()")
        plugin_system._app.input_handler.register_completer(completer)
    else:
        print(f"  → Condition failed, NOT registering")

plugin_system._register_completer = traced_register

# Now load plugin
plugin_path = Path(".aicoder/plugins/snippets.py")
spec = importlib.util.spec_from_file_location("plugin_snippets", str(plugin_path))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if hasattr(module, "create_plugin"):
    print(f"Calling create_plugin...")
    module.create_plugin(plugin_system.context)

    print(f"\nFinal state:")
    print(f"  InputHandler.completers: {len(input_handler.completers)}")
