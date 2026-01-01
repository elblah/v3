#!/usr/bin/env python
"""Debug completer registration - check plugin condition"""

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

# Check what ctx.app looks like
print(f"plugin_system.context.app: {plugin_system.context.app}")
print(f"hasattr(plugin_system.context.app, 'input_handler'): {hasattr(plugin_system.context.app, 'input_handler')}")
print(f"plugin_system.context.app.input_handler: {plugin_system.context.app.input_handler if hasattr(plugin_system.context.app, 'input_handler') else 'N/A'}")

# Now load plugin
plugin_path = Path(".aicoder/plugins/snippets.py")
spec = importlib.util.spec_from_file_location("plugin_snippets", str(plugin_path))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Patch the plugin's completer registration to see if it tries
import plugins.snippets as snippets_module
original_snippet_completer = None

# Load module and check what happens
if hasattr(module, "create_plugin"):
    # Read the plugin source to see the condition
    with open(plugin_path, 'r') as f:
        source = f.read()
        if "if hasattr(ctx.app, 'input_handler'):" in source:
            print("\n✓ Plugin checks for ctx.app.input_handler")
        else:
            print("\n✗ Plugin doesn't check for ctx.app.input_handler")
