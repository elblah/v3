#!/usr/bin/env python
"""Debug completer registration"""

import sys
import importlib.util
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aicoder.core.plugin_system import PluginSystem
from aicoder.core.input_handler import InputHandler

# Create input handler
input_handler = InputHandler()
print(f"InputHandler created: {input_handler}")
print(f"InputHandler.completers initial: {len(input_handler.completers)}")

# Create mock app
class MockApp:
    def __init__(self, ih):
        self.input_handler = ih

mock_app = MockApp(input_handler)
print(f"MockApp created with input_handler: {mock_app.input_handler}")

# Load plugin
plugin_system = PluginSystem()
print(f"PluginSystem created")

plugin_system.set_app(mock_app)
print(f"App set on plugin_system: {plugin_system._app}")
print(f"App.input_handler: {plugin_system._app.input_handler}")

plugin_path = Path(".aicoder/plugins/snippets.py")
print(f"Plugin path: {plugin_path}")
print(f"Plugin exists: {plugin_path.exists()}")

spec = importlib.util.spec_from_file_location("plugin_snippets", str(plugin_path))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

print(f"Module loaded, has create_plugin: {hasattr(module, 'create_plugin')}")

if hasattr(module, "create_plugin"):
    print(f"Calling create_plugin...")
    result = module.create_plugin(plugin_system.context)
    print(f"create_plugin returned: {result}")

    # Check if completer was registered
    print(f"InputHandler.completers after loading: {len(input_handler.completers)}")
    if len(input_handler.completers) > 0:
        print("✓ Completer successfully registered!")
    else:
        print("✗ Completer was NOT registered")
