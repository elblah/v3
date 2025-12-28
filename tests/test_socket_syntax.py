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
expected_methods = ['start', 'stop', '_cmd_is_processing', '_cmd_stop', '_cmd_yolo', '_cmd_stats', '_cmd_status', '_cmd_help']

for method in expected_methods:
    if method not in server_methods:
        print(f"✗ SocketServer missing method: {method}")
        sys.exit(1)

print(f"✓ SocketServer has all expected methods ({len(expected_methods)} found)")

print("\n" + "="*50)
print("All tests passed! Socket API is ready to use.")
print("Use: echo 'command' | nc -U $TMPDIR/aicoder-*.socket")
print("="*50)
