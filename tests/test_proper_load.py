#!/usr/bin/env python
"""Test plugin loading the proper way"""

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

# Load plugins (the proper way)
print("Loading plugins...")
plugin_system.load_plugins()

print(f"\nAfter loading:")
print(f"  Hooks: {list(plugin_system.hooks.keys())}")
print(f"  Commands: {list(plugin_system.commands.keys())}")
print(f"  InputHandler.completers: {len(input_handler.completers)}")

if len(input_handler.completers) > 0:
    print(f"\n✓ Completer registered successfully!")

    # Test completer
    completer = input_handler.completers[0]
    print(f"\nTesting completer:")
    result0 = completer("@@deb", 0)
    print(f"  completer('@@deb', 0) = {result0}")

    if result0:
        print(f"  ✓ Tab completion should work!")
else:
    print(f"\n✗ Completer was NOT registered")
