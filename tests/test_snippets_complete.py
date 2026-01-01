#!/usr/bin/env python
"""
Complete verification test for snippets plugin
Ensures all components work together correctly
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_plugin_installation():
    """Verify plugin is installed in correct location"""
    plugin_path = Path(".aicoder/plugins/snippets.py")

    if not plugin_path.exists():
        print("✗ Plugin not installed in .aicoder/plugins/")
        return False

    print(f"✓ Plugin installed at: {plugin_path}")

    # Verify plugin source also exists
    source_path = Path("plugins/snippets.py")
    if not source_path.exists():
        print("✗ Plugin source not found at plugins/snippets.py")
        return False

    print(f"✓ Plugin source exists at: {source_path}")
    return True


def test_snippets_directory():
    """Verify snippets directory and files exist"""
    snippets_dir = Path(".aicoder/snippets")

    if not snippets_dir.exists():
        print("✗ Snippets directory not found")
        return False

    print(f"✓ Snippets directory exists: {snippets_dir}")

    # Check for expected snippet files
    expected_snippets = [
        "ultrathink.md",
        "plan_mode.txt",
        "build_mode.txt",
        "debug_mode.md",
        "rethink"
    ]

    for snippet in expected_snippets:
        snippet_path = snippets_dir / snippet
        if not snippet_path.exists():
            print(f"✗ Missing snippet: {snippet}")
            return False

        # Verify snippet has content
        with open(snippet_path, 'r') as f:
            content = f.read()
            if not content.strip():
                print(f"✗ Snippet is empty: {snippet}")
                return False

        print(f"✓ Snippet exists with content: {snippet}")

    return True


def test_plugin_loading():
    """Test that plugin loads correctly"""
    from aicoder.core.plugin_system import PluginSystem

    class MockApp:
        def __init__(self):
            self.input_handler = None

    plugin_system = PluginSystem()
    plugin_system.set_app(MockApp())

    plugin_path = Path(".aicoder/plugins/snippets.py")
    if not plugin_path.exists():
        print("✗ Plugin file not found")
        return False

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "plugin_snippets", str(plugin_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "create_plugin"):
            print("✗ Plugin missing create_plugin function")
            return False

        result = module.create_plugin(plugin_system.context)
        print("✓ Plugin loaded successfully")

        # Verify registrations
        if 'after_user_prompt' in plugin_system.hooks:
            print("✓ Hook registered: after_user_prompt")
        else:
            print("✗ Hook not registered: after_user_prompt")
            return False

        if 'snippets' in plugin_system.commands:
            print("✓ Command registered: snippets")
        else:
            print("✗ Command not registered: snippets")
            return False

        return True

    except Exception as e:
        print(f"✗ Plugin loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_transformation_logic():
    """Test that snippet transformation works"""
    from aicoder.core.plugin_system import PluginSystem

    plugin_system = PluginSystem()
    plugin_system.set_app(None)

    plugin_path = Path(".aicoder/plugins/snippets.py")
    if not plugin_path.exists():
        print("✗ Plugin file not found")
        return False

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "plugin_snippets", str(plugin_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "create_plugin"):
            module.create_plugin(plugin_system.context)

            hooks = plugin_system.hooks.get("after_user_prompt", [])
            if not hooks:
                print("✗ No transformation hook")
                return False

            transform_fn = hooks[0]

            # Test with valid snippet
            result = transform_fn("Use @@ultrathink to analyze")
            if "@@ultrathink" not in result and "Yagnot Foravah" in result:
                print("✓ Valid snippet replacement works")
            else:
                print("✗ Valid snippet replacement failed")
                return False

            # Test with invalid snippet
            result = transform_fn("Use @@nonexistent to analyze")
            if "@@nonexistent" in result:
                print("✓ Invalid snippet handling works (preserves @@)")
            else:
                print("✗ Invalid snippet handling failed")
                return False

            # Test with no snippets
            result = transform_fn("Just a normal prompt")
            if result == "Just a normal prompt":
                print("✓ Normal prompt unchanged")
            else:
                print("✗ Normal prompt changed unexpectedly")
                return False

            return True

    except Exception as e:
        print(f"✗ Transformation test failed: {e}")
        return False


def test_completer_registration():
    """Test that completer can be registered"""
    from aicoder.core.plugin_system import PluginSystem
    from aicoder.core.input_handler import InputHandler

    # Create input handler
    input_handler = InputHandler()

    # Create mock app with input_handler
    class MockApp:
        def __init__(self):
            self.input_handler = input_handler

    mock_app = MockApp()

    # Load plugin
    plugin_system = PluginSystem()
    plugin_system.set_app(mock_app)

    plugin_path = Path(".aicoder/plugins/snippets.py")
    if not plugin_path.exists():
        print("✗ Plugin file not found")
        return False

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "plugin_snippets", str(plugin_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "create_plugin"):
            module.create_plugin(plugin_system.context)

            # Verify completer was registered
            if len(input_handler.completers) > 0:
                print(f"✓ Completer registered ({len(input_handler.completers)} completer(s))")
            else:
                print("✗ No completer registered")
                return False

            return True

    except Exception as e:
        print(f"✗ Completer registration test failed: {e}")
        return False


def main():
    """Run all verification tests"""
    print("=" * 70)
    print("COMPLETE VERIFICATION: Snippets Plugin")
    print("=" * 70)

    os.chdir(Path(__file__).parent.parent)

    tests = [
        ("Plugin Installation", test_plugin_installation),
        ("Snippets Directory", test_snippets_directory),
        ("Plugin Loading", test_plugin_loading),
        ("Transformation Logic", test_transformation_logic),
        ("Completer Registration", test_completer_registration),
    ]

    all_passed = True
    for test_name, test_fn in tests:
        print(f"\n{test_name}:")
        print("-" * 70)
        if not test_fn():
            all_passed = False
        print()

    print("=" * 70)
    if all_passed:
        print("✓ ALL VERIFICATION TESTS PASSED")
        print("=" * 70)
        print("\nThe snippets plugin is ready to use!")
        print("\nTry these commands:")
        print("  python main.py")
        print("  > @@<Tab>                    # See available snippets")
        print("  > Use @@ultrathink to analyze # Try using a snippet")
        print("  > /snippets                  # List all snippets")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
