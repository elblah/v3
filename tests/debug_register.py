#!/usr/bin/env python
"""Trace what happens in _register_completer"""

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

# Create plugin system and set app
plugin_system = PluginSystem()
plugin_system.set_app(mock_app)

# Now manually call _register_completer with a test function
def test_completer(text, state):
    return f"test_{text}_{state}"

print(f"Before calling _register_completer:")
print(f"  plugin_system._app: {plugin_system._app}")
print(f"  plugin_system._app.input_handler: {plugin_system._app.input_handler}")
print(f"  input_handler.completers: {len(input_handler.completers)}")

print(f"\nCalling _register_completer(test_completer)...")
plugin_system._register_completer(test_completer)

print(f"\nAfter calling _register_completer:")
print(f"  input_handler.completers: {len(input_handler.completers)}")

if len(input_handler.completers) > 0:
    print(f"✓ Completer registered successfully!")
else:
    print(f"✗ Completer was NOT registered")
    print(f"\nCondition check:")
    print(f"  self._app: {plugin_system._app}")
    print(f"  self._app.input_handler: {plugin_system._app.input_handler if plugin_system._app else None}")
    print(f"  Both True?: {plugin_system._app is not None and plugin_system._app.input_handler is not None}")
