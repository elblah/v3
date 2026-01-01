#!/usr/bin/env python
"""Debug completer registration - detailed"""

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

plugin_path = Path(".aicoder/plugins/snippets.py")
spec = importlib.util.spec_from_file_location("plugin_snippets", str(plugin_path))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

print(f"Module loaded")
print(f"hasattr(module, 'create_plugin'): {hasattr(module, 'create_plugin')}")

if hasattr(module, "create_plugin"):
    # Call create_plugin directly
    print(f"\nCalling create_plugin...")

    # Patch the registration to see if it's called
    original_register = plugin_system.context.register_completer
    call_count = [0]

    def traced_register(completer):
        call_count[0] += 1
        print(f"  → register_completer called! (call #{call_count[0]})")
        return original_register(completer)

    plugin_system.context.register_completer = traced_register

    result = module.create_plugin(plugin_system.context)

    print(f"\nregister_completer was called {call_count[0]} time(s)")
    print(f"InputHandler.completers: {len(input_handler.completers)}")
    print(f"plugin_system._app: {plugin_system._app}")
    print(f"plugin_system._app.input_handler: {plugin_system._app.input_handler if plugin_system._app else None}")
