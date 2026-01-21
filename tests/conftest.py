"""
Global test fixtures for all tests
"""

import pytest

from aicoder.core.token_estimator import clear_cache, _message_cache, _tools_tokens


@pytest.fixture(autouse=True)
def clear_token_cache():
    """Clear token estimator cache before each test to prevent state contamination"""
    print(f"\n[CONFTEST] Before test: cache size={len(_message_cache)}, tools_tokens={_tools_tokens}")
    # Clear message cache and reset tool tokens to 0 for testing
    from aicoder.core import token_estimator
    token_estimator._message_cache.clear()
    token_estimator._tools_tokens = 0
    token_estimator._original_tool_tokens = 0
    print(f"[CONFTEST] After clear: cache size={len(token_estimator._message_cache)}, tools_tokens={token_estimator._tools_tokens}")
    yield
