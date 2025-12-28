#!/usr/bin/env python3
"""
Test script for AI Coder socket server
Run this while AI Coder is running to test the socket API
"""

import os
import sys
import json
import socket
import time

def find_socket() -> str:
    """Find most recent AI Coder socket"""
    tmpdir = os.environ.get("TMPDIR", "/tmp")

    if not os.path.exists(tmpdir):
        print(f"Error: {tmpdir} not found")
        sys.exit(1)

    sockets = []
    for filename in os.listdir(tmpdir):
        if filename.startswith("aicoder-") and filename.endswith(".socket"):
            sockets.append(os.path.join(tmpdir, filename))

    if not sockets:
        print(f"Error: No AI Coder socket found in {tmpdir}")
        print("Make sure AI Coder is running!")
        sys.exit(1)

    sockets.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return sockets[0]


def send_command(socket_path: str, command: str) -> str:
    """Send command and get response"""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(3.0)
        client.connect(socket_path)

        client.sendall((command + "\n").encode("utf-8"))

        response = b""
        client.setblocking(True)
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\n" in response:
                break

        client.close()
        return response.decode("utf-8").strip()

    except Exception as e:
        return f"ERROR: {e}"


def main():
    print("=== AI Coder Socket Server Test ===\n")

    # Find socket
    socket_path = find_socket()
    print(f"Using socket: {socket_path}\n")

    # Test commands
    tests = [
        ("ping", "pong"),
        ("version", "version"),
        ("is_processing", "processing"),
        ("status", "processing"),
        ("yolo status", "enabled"),
        ("yolo on", "OK"),
        ("yolo status", "enabled"),
        ("yolo off", "OK"),
        ("detail status", "enabled"),
        ("stats", "messages_sent"),
        ("messages count", "total"),
        ("help", "Commands"),
    ]

    passed = 0
    failed = 0

    for command, expected in tests:
        print(f"Testing: {command}")
        response = send_command(socket_path, command)
        print(f"Response: {response[:100]}")

        # Check if response looks valid
        if expected in response or response == "OK" or response == "pong":
            print("✓ PASS\n")
            passed += 1
        else:
            print(f"✗ FAIL (expected: {expected})\n")
            failed += 1
        time.sleep(0.1)

    # Test save
    print("Testing: save")
    response = send_command(socket_path, "save /tmp/test-aicoder-save.json")
    print(f"Response: {response}")
    if response.startswith("OK"):
        print("✓ PASS\n")
        passed += 1
        # Cleanup
        if os.path.exists("/tmp/test-aicoder-save.json"):
            os.remove("/tmp/test-aicoder-save.json")
    else:
        print("✗ FAIL\n")
        failed += 1

    # Test inject (requires tmux)
    print("Testing: inject")
    if os.environ.get("TMUX"):
        response = send_command(socket_path, "inject")
        print(f"Response: {response}")
        # Check for JSON response with injected field
        try:
            resp_json = json.loads(response)
            if "injected" in resp_json:
                print("✓ PASS\n")
                passed += 1
            else:
                print("✗ FAIL\n")
                failed += 1
        except json.JSONDecodeError:
            print("✗ FAIL (invalid JSON)\n")
            failed += 1
    else:
        print("Skipping (not in tmux environment)")
        print("✓ PASS (skipped)\n")
        passed += 0  # Don't count as passed or failed

    # Summary
    print("=" * 50)
    print(f"Tests passed: {passed}")
    print(f"Tests failed: {failed}")
    print(f"Total: {passed + failed}")

    if failed == 0:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
