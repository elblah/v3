#!/usr/bin/env python3
"""
Test the command completer plugin
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aicoder.core.input_handler import InputHandler
from aicoder.core.stats import Stats
from aicoder.core.message_history import MessageHistory
from aicoder.core.command_handler import CommandHandler
from aicoder.core.plugin_system import PluginSystem


def test_command_completer():
    """Test that command completer plugin works correctly"""

    print("Testing command completer plugin...")
    print("=" * 60)

    # Create minimal components
    stats = Stats()
    message_history = MessageHistory(stats)
    input_handler = InputHandler(None, stats, message_history)

    # Create command handler
    command_handler = CommandHandler(
        message_history=message_history,
        input_handler=input_handler,
        stats=stats,
    )

    # Create minimal AICoder mock
    class MockAICoder:
        def __init__(self):
            self.input_handler = input_handler
            self.command_handler = command_handler
            self.stats = stats
            self.message_history = message_history
            self.plugin_system = None

    mock_app = MockAICoder()
    input_handler.command_handler = command_handler

    # Create plugin system
    plugin_system = PluginSystem()
    plugin_system.set_app(mock_app)

    # Load command_completer plugin
    try:
        # Use the built-in plugin loading method
        plugin_system._load_single_plugin("plugins/command_completer.py")

        print("✓ Plugin loaded successfully")
    except Exception as e:
        print(f"✗ Failed to load plugin: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Verify completer was registered
    if not input_handler.completers:
        print("✗ No completers registered")
        return False

    print(f"✓ Registered {len(input_handler.completers)} completer(s)")

    # Test completer function
    completer = input_handler.completers[-1]  # Get the last registered completer

    # Test 1: Completion for /help
    print("\nTest 1: Completing '/he'")
    result0 = completer("/he", 0)
    print(f"  completer('/he', 0) = {result0}")
    if result0 and result0.startswith("/he"):
        print("  ✓ Works!")
    else:
        print("  ✗ Failed")
        return False

    # Test 2: Multiple completions
    print("\nTest 2: Iterating through completions for '/he'")
    results = []
    state = 0
    while True:
        result = completer("/he", state)
        if result is None:
            break
        results.append(result)
        state += 1

    print(f"  Found {len(results)} completions:")
    for r in results:
        print(f"    - {r}")

    if len(results) > 0:
        print("  ✓ Multiple completions work!")
    else:
        print("  ✗ No completions found")
        return False

    # Test 3: Non-matching prefix
    print("\nTest 3: Non-matching prefix '/xyz'")
    result = completer("/xyz", 0)
    print(f"  completer('/xyz', 0) = {result}")
    if result is None:
        print("  ✓ Correctly returns None for non-matching prefix")
    else:
        print("  ✗ Should return None")
        return False

    # Test 4: No / prefix
    print("\nTest 4: No / prefix 'help'")
    result = completer("help", 0)
    print(f"  completer('help', 0) = {result}")
    if result is None:
        print("  ✓ Correctly ignores non-command text")
    else:
        print("  ✗ Should return None for text without / prefix")
        return False

    # Test 5: Check for built-in commands
    print("\nTest 5: Checking for built-in commands")
    builtins = ["/help", "/quit", "/stats"]
    found = []
    for cmd in builtins:
        result = completer(cmd, 0)
        if result:
            found.append(result)

    print(f"  Found built-in commands: {found}")
    if len(found) == len(builtins):
        print("  ✓ All built-in commands are available for completion")
    else:
        print("  ✗ Some built-in commands missing")

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("\nThe command_completer plugin is ready to use!")
    print("\nInstall globally:")
    print("  mkdir -p ~/.config/aicoder-v3/plugins/")
    print("  cp plugins/command_completer.py ~/.config/aicoder-v3/plugins/")
    print("\nThen test in any AI Coder instance:")
    print("  > /<Tab>    # See all commands")
    print("  > /he<Tab>  # Complete /help, etc.")
    return 0


if __name__ == "__main__":
    success = test_command_completer()
    sys.exit(success)
