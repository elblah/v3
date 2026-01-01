"""Integration test for snippets plugin - actual file replacement"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_real_snippet_replacement():
    """Test that real snippets are replaced correctly"""
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

            # Get transformation hook
            hooks = plugin_system.hooks.get("after_user_prompt", [])
            if not hooks:
                print("✗ No transformation hook registered")
                return False

            transform_fn = hooks[0]

            # Test 1: Replace ultrathink snippet
            prompt = "Use @@ultrathink to analyze the code"
            result = transform_fn(prompt)

            if "@@ultrathink" not in result:
                print("✓ Snippet replacement works for ultrathink.md")
                # Verify some content from the file
                if "Yagnot Foravah" in result:
                    print("✓ Content correctly loaded from ultrathink.md")
                else:
                    print("✗ Content not found in replacement")
                    return False
            else:
                print("✗ Snippet not replaced: @@ultrathink still in result")
                print(f"Result: {result}")
                return False

            # Test 2: Replace plan_mode snippet
            prompt = "Follow @@plan_mode for this task"
            result = transform_fn(prompt)

            if "@@plan_mode" not in result:
                print("✓ Snippet replacement works for plan_mode.txt")
                if "structured approach" in result.lower():
                    print("✓ Content correctly loaded from plan_mode.txt")
                else:
                    print("✗ Content not found in replacement")
                    return False
            else:
                print("✗ Snippet not replaced: @@plan_mode still in result")
                return False

            # Test 3: Multiple snippets in one prompt
            prompt = "Use @@debug_mode and @@rethink to solve this"
            result = transform_fn(prompt)

            if "@@debug_mode" not in result and "@@rethink" not in result:
                print("✓ Multiple snippets replaced correctly")
            else:
                print("✗ Multiple snippets not fully replaced")
                return False

            # Test 4: Snippet without extension (rethink has no extension)
            prompt = "Apply @@rethink"
            result = transform_fn(prompt)

            if "@@rethink" not in result:
                print("✓ Snippet without extension works")
            else:
                print("✗ Snippet without extension not replaced")
                return False

            return True

    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Integration Test: Real Snippet Replacement")
    print("=" * 60)

    # Change to project directory
    os.chdir(Path(__file__).parent.parent)

    if test_real_snippet_replacement():
        print("\n" + "=" * 60)
        print("✓ All integration tests passed!")
    else:
        print("\n" + "=" * 60)
        print("✗ Integration test failed")
        sys.exit(1)
