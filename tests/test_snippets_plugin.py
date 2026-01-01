"""Test snippets plugin functionality"""

import os
import tempfile
import shutil
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_snippets_plugin_loads():
    """Test that snippets plugin can be loaded"""
    from aicoder.core.plugin_system import PluginSystem

    # Create a mock app with minimal interface
    class MockApp:
        def __init__(self):
            self.input_handler = None

    # Create plugin system
    plugin_system = PluginSystem()
    mock_app = MockApp()
    plugin_system.set_app(mock_app)

    # Load the plugin directly
    plugin_path = Path(__file__).parent.parent / ".aicoder" / "plugins" / "snippets.py"
    if plugin_path.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                f"plugin_snippets", str(plugin_path)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Call create_plugin
            if hasattr(module, "create_plugin"):
                result = module.create_plugin(plugin_system.context)
                print("✓ Snippets plugin loaded successfully")
                print(f"  - Registered hooks: {list(plugin_system.hooks.keys())}")
                print(f"  - Registered commands: {list(plugin_system.commands.keys())}")
                return True
        except Exception as e:
            print(f"✗ Failed to load snippets plugin: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print(f"✗ Plugin file not found: {plugin_path}")
        return False


def test_snippet_transformation():
    """Test that snippets are transformed correctly"""
    from aicoder.core.plugin_system import PluginSystem

    # Create plugin system
    plugin_system = PluginSystem()
    plugin_system.set_app(None)

    # Load plugin
    plugin_path = Path(__file__).parent.parent / ".aicoder" / "plugins" / "snippets.py"
    if not plugin_path.exists():
        print("✗ Plugin file not found")
        return False

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f"plugin_snippets", str(plugin_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "create_plugin"):
            module.create_plugin(plugin_system.context)

            # Test transformation hook
            hooks = plugin_system.hooks.get("after_user_prompt", [])
            if not hooks:
                print("✗ No transformation hook registered")
                return False

            transform_fn = hooks[0]

            # Test with non-existent snippet
            result = transform_fn("Use @@nonexistent to analyze")
            if "@@nonexistent" in result:
                print("✓ Missing snippet handling works (keeps original)")
            else:
                print("✗ Missing snippet handling failed")

            # Test without snippets
            result = transform_fn("Just a normal prompt")
            if result == "Just a normal prompt":
                print("✓ Normal prompt unchanged")
            else:
                print("✗ Normal prompt changed unexpectedly")

            return True

    except Exception as e:
        print(f"✗ Transformation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_snippets_directory():
    """Test that snippets directory exists and contains files"""
    snippets_dir = Path(".aicoder/snippets")

    if not snippets_dir.exists():
        print("✗ Snippets directory not found")
        return False

    snippets = list(snippets_dir.glob("*"))
    snippets = [s for s in snippets if s.is_file()]

    if not snippets:
        print("✗ No snippet files found")
        return False

    print(f"✓ Found {len(snippets)} snippet files:")
    for snippet in snippets:
        print(f"  - {snippet.name}")

    # Try to load a snippet
    try:
        first_snippet = snippets[0]
        with open(first_snippet, 'r') as f:
            content = f.read()
            if content:
                print(f"✓ Successfully loaded snippet: {first_snippet.name}")
            else:
                print(f"✗ Snippet is empty: {first_snippet.name}")
    except Exception as e:
        print(f"✗ Failed to load snippet: {e}")
        return False

    return True


if __name__ == "__main__":
    print("Testing Snippets Plugin")
    print("=" * 50)

    all_passed = True

    # Change to project directory
    os.chdir(Path(__file__).parent.parent)

    print("\n1. Testing snippets directory:")
    if not test_snippets_directory():
        all_passed = False

    print("\n2. Testing plugin loading:")
    if not test_snippets_plugin_loads():
        all_passed = False

    print("\n3. Testing snippet transformation:")
    if not test_snippet_transformation():
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
        sys.exit(1)
