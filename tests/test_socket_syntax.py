#!/usr/bin/env python3
"""Quick test to verify socket server syntax and imports"""

import sys

print("Testing socket API imports...")

try:
    from aicoder.core.socket_server import SocketServer
    print("✓ SocketServer imports successfully")
except ImportError as e:
    print(f"✗ SocketServer import failed: {e}")
    sys.exit(1)

try:
    from aicoder.core.aicoder import AICoder
    print("✓ AICoder imports successfully")
except ImportError as e:
    print(f"✗ AICoder import failed: {e}")
    sys.exit(1)

# Check that SocketServer class has expected methods
server_methods = [m for m in dir(SocketServer)]

# Core methods
core_methods = ['start', 'stop']
for method in core_methods:
    if method not in server_methods:
        print(f"✗ SocketServer missing method: {method}")
        sys.exit(1)

# Command handlers
cmd_methods = [
    '_cmd_command',      # Main command handler
    '_cmd_detail',        # Toggle detail mode
    '_cmd_inject',        # Inject message with tools
    '_cmd_inject_text',   # Inject text message
    '_cmd_is_processing',  # Check if processing
    '_cmd_kill',          # Kill current process
    '_cmd_messages',       # Get message count
    '_cmd_process',        # Process command
    '_cmd_quit',          # Quit
    '_cmd_sandbox',       # Toggle sandbox
    '_cmd_save',          # Save state
    '_cmd_status',         # Get status
    '_cmd_stop',          # Stop
    '_cmd_yolo',          # Toggle YOLO mode
]

for method in cmd_methods:
    if method not in server_methods:
        print(f"✗ SocketServer missing method: {method}")
        sys.exit(1)

print(f"✓ SocketServer has all expected methods ({len(core_methods) + len(cmd_methods)} found)")

print("\n" + "="*50)
print("All tests passed! Socket API is ready to use.")
print("Use: echo 'command' | nc -U $TMPDIR/aicoder-*.socket")
print("="*50)
