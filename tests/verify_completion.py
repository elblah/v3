#!/usr/bin/env python3
"""
Verify that command completion setup is correct
"""

import readline
import os
import sys

print("=" * 60)
print("Verifying Command Completion Setup")
print("=" * 60)

# Check 1: Delimiters
print("\n1. Checking readline word delimiters:")
delims = readline.get_completer_delims()
print(f"   Current delimiters: {repr(delims)}")

if '@' in delims:
    print("   ✗ '@' is still a delimiter - @@ completion should NOT work")
else:
    print("   ✓ '@' is NOT a delimiter - @@ completion should work")

if '-' in delims:
    print("   ✗ '-' is still a delimiter")
else:
    print("   ✓ '-' is NOT a delimiter")

if '/' in delims:
    print("   ✗ '/' is still a delimiter - /command completion will NOT work")
else:
    print("   ✓ '/' is NOT a delimiter - /command completion should work")

# Check 2: Plugin file
print("\n2. Checking plugin file existence:")
global_plugins_dir = os.path.expanduser("~/.config/aicoder-v3/plugins")
plugin_path = os.path.join(global_plugins_dir, "command_completer.py")

if os.path.exists(plugin_path):
    print(f"   ✓ Plugin exists at: {plugin_path}")

    # Check if it has debug
    with open(plugin_path, 'r') as f:
        content = f.read()
        if "[command_completer]" in content:
            print("   ✓ Plugin has debug statements")
        else:
            print("   ✗ Plugin does NOT have debug statements (copy the updated version)")
else:
    print(f"   ✗ Plugin NOT found at: {plugin_path}")
    print(f"   Directory exists: {os.path.exists(global_plugins_dir)}")

# Check 3: Instructions
print("\n3. Setup Instructions:")
print("   If you see ✗ above, here's what to do:")
print()
print("   a) Ensure input_handler.py has the delimiter fix:")
print("      delims = readline.get_completer_delims().replace('@', '').replace('-', '').replace('/', '')")
print()
print("   b) Copy the plugin with debug:")
print("      cp plugins/command_completer.py ~/.config/aicoder-v3/plugins/")
print()
print("   c) Restart AI Coder")
print("   d) Type: /<Tab> and look for '[command_completer]' debug output")
print()

print("=" * 60)
print("Done!")
print("=" * 60)
