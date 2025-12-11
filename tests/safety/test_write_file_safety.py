#!/usr/bin/env python3

"""
Basic safety test for write_file tool.
Tests the exact warning format and behavior when AI tries to write without reading first.
"""

import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.utils.test_harness import TestHarness, TestPatterns
from tests.utils.message_injector import ToolCall


def test_write_file_safety_violation():
    """
    Test write_file safety violation scenario.
    
    Expected behavior:
    - Show warning in exact format
    - Not write the file
    - Use yellow color for warning
    - Correct order: tool header, path, warning
    """
    print("Testing write_file safety violation...")
    
    harness = TestHarness()
    try:
        # Setup AI Coder
        harness.setup_aicoder()
        
        # Test with TestPatterns utility
        test_file = "test_safety.txt"
        results = TestPatterns.safety_violation_test(harness, "write_file", test_file)
        
        # Print detailed results for debugging
        print(f"Test file: {results['file_path']}")
        print(f"Output lines ({len(results['output_lines'])}):")
        for i, line in enumerate(results['output_lines']):
            print(f"  {i}: {repr(line)}")
        
        print(f"\nFormat results: {results['format_results']}")
        print(f"Violation count: {results['violation_count']}")
        print(f"Successful tool results: {len(results['successful_results'])}")
        print(f"Errors: {results['errors']}")
        print(f"Test passed: {results['test_passed']}")
        
        # Verify file was not created/modified
        file_exists = os.path.exists(results['file_path'])
        print(f"File exists after test: {file_exists}")
        
        if file_exists:
            with open(results['file_path'], 'r') as f:
                content = f.read()
            print(f"File content: {repr(content)}")
        
        # Return test results for verification
        return results
    finally:
        harness.cleanup()


def test_write_file_new_file_no_warning():
    """
    Test that new file creation doesn't trigger safety warning.
    """
    print("\nTesting write_file new file creation (no warning expected)...")
    
    harness = TestHarness()
    try:
        harness.setup_aicoder()
        
        # Use a file that doesn't exist
        new_file = "truly_new_file.txt"
        file_path = harness.get_test_file_path(new_file)
        
        # Ensure file doesn't exist
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Create write tool call
        tool_call = ToolCall(
            id="test_new",
            function_name="write_file",
            arguments={"path": new_file, "content": "new file content"}
        )
        
        # Inject and capture
        output_lines, tool_results = harness.inject_and_capture([tool_call])
        
        print(f"Output lines ({len(output_lines)}):")
        for i, line in enumerate(output_lines):
            print(f"  {i}: {repr(line)}")
        
        # Check for warnings
        violation_count = harness.count_safety_violations(output_lines)
        successful_results = harness.get_tool_execution_results(tool_results)
        errors = harness.get_tool_execution_errors(tool_results)
        
        print(f"Violation count: {violation_count}")
        print(f"Successful results: {len(successful_results)}")
        print(f"Errors: {errors}")
        
        # Verify file was created
        full_path = harness.get_test_file_path(new_file)
        file_exists = os.path.exists(full_path)
        print(f"Checking file at: {full_path}")
        print(f"File exists after test: {file_exists}")
        print(f"Test directory: {harness.temp_dir}")
        print(f"Files in test directory: {os.listdir(harness.temp_dir)}")
        
        if file_exists:
            with open(full_path, 'r') as f:
                content = f.read()
            print(f"Final file content: {repr(content)}")
        
        return {
            "violation_count": violation_count,
            "successful_results": successful_results,
            "errors": errors,
            "file_created": file_exists,
            "test_passed": violation_count == 0 and len(successful_results) > 0 and file_exists
        }
    finally:
        harness.cleanup()


def test_write_file_read_then_write():
    """
    Test that reading then writing file doesn't trigger safety warning.
    """
    print("\nTesting read then write (no warning expected)...")
    
    harness = TestHarness()
    try:
        harness.setup_aicoder()
        
        # Create existing file
        test_file = "existing_file.txt"
        harness.create_test_file(test_file, "original content")
        file_path = harness.get_test_file_path(test_file)
        
        # Create tool calls: read then write
        tool_calls = [
            ToolCall(
                id="test_read",
                function_name="read_file",
                arguments={"path": test_file}
            ),
            ToolCall(
                id="test_write",
                function_name="write_file",
                arguments={"path": test_file, "content": "modified content"}
            )
        ]
        
        # Inject and capture
        output_lines, tool_results = harness.inject_and_capture(tool_calls)
        
        print(f"Output lines ({len(output_lines)}):")
        for i, line in enumerate(output_lines):
            print(f"  {i}: {repr(line)}")
        
        # Check for warnings
        violation_count = harness.count_safety_violations(output_lines)
        successful_results = harness.get_tool_execution_results(tool_results)
        errors = harness.get_tool_execution_errors(tool_results)
        
        print(f"Violation count: {violation_count}")
        print(f"Successful results: {len(successful_results)}")
        print(f"Errors: {errors}")
        
        # Verify file was modified
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
            print(f"Final file content: {repr(content)}")
        
        return {
            "violation_count": violation_count,
            "successful_results": successful_results,
            "errors": errors,
            "file_modified": content == "modified content" if 'content' in locals() else False,
            "test_passed": violation_count == 0 and len(successful_results) >= 1
        }
    finally:
        harness.cleanup()


if __name__ == "__main__":
    print("Running write_file safety tests...")
    print("=" * 60)
    
    # Run all tests
    test1_results = test_write_file_safety_violation()
    test2_results = test_write_file_new_file_no_warning() 
    test3_results = test_write_file_read_then_write()
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"Test 1 (safety violation): {'PASS' if test1_results['test_passed'] else 'FAIL'}")
    print(f"Test 2 (new file): {'PASS' if test2_results['test_passed'] else 'FAIL'}")
    print(f"Test 3 (read then write): {'PASS' if test3_results['test_passed'] else 'FAIL'}")
    
    # Check if any critical issues
    all_passed = all([
        test1_results['test_passed'],
        test2_results['test_passed'], 
        test3_results['test_passed']
    ])
    
    print(f"\nAll tests passed: {'YES' if all_passed else 'NO'}")
    
    if not all_passed:
        print("\nISSUES FOUND:")
        if not test1_results['test_passed']:
            print("- Safety violation test failed - warning format incorrect")
        if not test2_results['test_passed']:
            print("- New file test failed - false positive warning")
        if not test3_results['test_passed']:
            print("- Read then write test failed - false positive warning")
        sys.exit(1)
    else:
        print("All tests passed successfully!")
        sys.exit(0)