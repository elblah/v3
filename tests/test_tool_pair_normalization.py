"""
Regression tests for tool-call / tool-result pairing.

Background: a plugin (vision) used to inject a user message from INSIDE a tool
call. The message was appended immediately, so history and the session file
ended up as:

    assistant(tool_calls=[call_1])
    user("This is the image you requested: ...")
    tool(call_1, "Image loaded")

On reload the runtime did not see the output right after the call, injected a
placeholder, and the provider answered with HTTP 400
"Duplicate function_call_output for call_id 'call_1'" on every single request.

These tests pin the three defenses:
  1. plugin messages are deferred while a tool chain is open;
  2. normalization collapses duplicates / fixes order;
  3. the "ensure responses" pass never creates a second output.
"""

import pytest

from aicoder.core.message_history import (
    CANCELLED_TOOL_OUTPUT,
    MessageHistory,
)
from aicoder.core.session_manager import SessionManager


@pytest.fixture
def message_history():
    from aicoder.core.stats import Stats
    return MessageHistory(Stats())


def _add_tool_calls(message_history, call_ids):
    """Seed an assistant message carrying tool_calls."""
    message_history.add_assistant_message({
        "role": "assistant",
        "content": "Calling tools",
        "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": "test", "arguments": "{}"}}
            for cid in call_ids
        ],
    })


def _tool_msg(call_id, content):
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _poisoned_history(message_history):
    """Reproduce the exact shape found in the broken session file (raw list).

    Assigned directly on purpose: the point is to test the repair passes, not
    the load path (which has its own test below).
    """
    message_history.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "look at this screenshot"},
        {
            "role": "assistant",
            "content": "Reading the image",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_image", "arguments": "{}"},
                }
            ],
        },
        {"role": "user", "content": "This is the image you requested: path=/app/x.png"},
        _tool_msg("call_1", "Image loaded: /app/x.png"),
        {"role": "assistant", "content": "I see a window"},
    ]
    return message_history.messages


def _outputs_per_call(messages):
    counts = {}
    for msg in messages:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            counts[msg["tool_call_id"]] = counts.get(msg["tool_call_id"], 0) + 1
    return counts


def _fake_session_manager(message_history):
    """SessionManager without running __init__ (no client, no file system)."""
    manager = object.__new__(SessionManager)
    manager.message_history = message_history
    return manager


def test_plugin_message_deferred_while_tool_chain_open(message_history):
    """A user message added inside a tool call must land AFTER the result."""
    _add_tool_calls(message_history, ["call_1"])

    message_history.add_user_message("This is the image you requested")

    # Not in the history yet: appending would split the pair.
    assert len(message_history.messages) == 1
    assert message_history.has_open_tool_chain() is True

    message_history.add_tool_results([{"tool_call_id": "call_1", "content": "Image loaded"}])

    roles = [m["role"] for m in message_history.messages]
    assert roles == ["assistant", "tool", "user"]
    assert message_history.messages[-1]["content"] == "This is the image you requested"
    assert message_history.has_open_tool_chain() is False


def test_multimodal_plugin_message_deferred(message_history):
    """The vision plugin passes a multimodal dict, not a string."""
    _add_tool_calls(message_history, ["call_1"])

    multimodal = {
        "role": "user",
        "content": [
            {"type": "text", "text": "This is the image you requested"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ],
    }
    message_history.add_user_message(multimodal)
    message_history.add_tool_results([{"tool_call_id": "call_1", "content": "Image loaded"}])

    assert [m["role"] for m in message_history.messages] == ["assistant", "tool", "user"]
    assert message_history.messages[-1] is multimodal


def test_deferred_message_flushed_when_chain_closes_on_error(message_history):
    """If the turn ends without tool results, the queue must not be lost."""
    _add_tool_calls(message_history, ["call_1"])
    message_history.add_user_message("queued while chain open")

    # Error path: next turn starts straight with an assistant message.
    message_history.add_assistant_message({"role": "assistant", "content": "recovered"})

    contents = [m.get("content") for m in message_history.messages]
    assert "queued while chain open" in contents
    assert contents.index("queued while chain open") == 1


def test_normalize_orders_outputs_after_call(message_history):
    """assistant -> user -> tool becomes assistant -> tool -> user."""
    _poisoned_history(message_history)

    message_history.normalize_tool_pairs()

    roles = [m["role"] for m in message_history.messages]
    assert roles == ["system", "user", "assistant", "tool", "user", "assistant"]
    assert message_history.messages[3]["tool_call_id"] == "call_1"
    assert _outputs_per_call(message_history.messages) == {"call_1": 1}


def test_normalize_collapses_duplicate_preferring_real_result(message_history):
    """Placeholder + real output for the same call collapse to the real one."""
    message_history.set_messages([
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_image", "arguments": "{}"},
                }
            ],
        },
        _tool_msg("call_1", "real result"),
        _tool_msg("call_1", CANCELLED_TOOL_OUTPUT),
        {"role": "assistant", "content": "done"},
    ])

    outputs = [m for m in message_history.messages if m.get("role") == "tool"]
    assert len(outputs) == 1
    assert outputs[0]["content"] == "real result"


def test_normalize_drops_orphan_tool_output(message_history):
    """An output without a matching call is removed instead of poisoning."""
    message_history.set_messages([
        {"role": "user", "content": "hi"},
        _tool_msg("call_ghost", "orphan"),
        {"role": "assistant", "content": "done"},
    ])

    assert [m["role"] for m in message_history.messages] == ["user", "assistant"]


def test_ensure_tool_responses_does_not_duplicate(message_history):
    """The exact bug: don't insert a placeholder when a real output exists later."""
    _poisoned_history(message_history)
    manager = _fake_session_manager(message_history)

    manager._ensure_tool_calls_have_responses()

    counts = _outputs_per_call(message_history.messages)
    assert counts == {"call_1": 1}
    outputs = [m for m in message_history.messages if m.get("role") == "tool"]
    assert outputs[0]["content"] != CANCELLED_TOOL_OUTPUT


def test_ensure_tool_responses_inserts_only_missing(message_history):
    """A genuinely unanswered call still gets its placeholder, exactly once."""
    message_history.set_messages([
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        _tool_msg("call_1", "real result"),
    ])
    manager = _fake_session_manager(message_history)

    manager._ensure_tool_calls_have_responses()

    counts = _outputs_per_call(message_history.messages)
    assert counts == {"call_1": 1, "call_2": 1}
    placeholders = [
        m for m in message_history.messages
        if m.get("role") == "tool" and m.get("content") == CANCELLED_TOOL_OUTPUT
    ]
    assert len(placeholders) == 1
    # Outputs stay directly after the assistant message, in call order.
    roles = [m["role"] for m in message_history.messages]
    assert roles == ["user", "assistant", "tool", "tool"]


def test_normalize_is_idempotent(message_history):
    """Running it twice must not change anything the second time."""
    _poisoned_history(message_history)
    assert message_history.normalize_tool_pairs() == 1
    healed = [dict(m) for m in message_history.messages]

    assert message_history.normalize_tool_pairs() == 0
    assert message_history.messages == healed


def test_repair_check_is_cheap_and_read_only(message_history):
    """The pre-request check must not touch a valid history."""
    message_history.set_messages([
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}}
            ],
        },
        _tool_msg("call_1", "ok"),
        {"role": "assistant", "content": "done"},
    ])
    snapshot = list(message_history.messages)

    assert message_history._tool_pairs_need_repair() is False
    assert message_history.normalize_tool_pairs() == 0
    assert message_history.messages == snapshot


def test_repair_check_detects_mid_chain_user(message_history):
    """The exact poisoned shape is flagged, so no request goes out malformed."""
    _poisoned_history(message_history)

    assert message_history._tool_pairs_need_repair() is True
    assert message_history.normalize_tool_pairs() == 1
    assert message_history._tool_pairs_need_repair() is False


def test_repair_check_detects_duplicate_and_orphan(message_history):
    message_history.messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}}
            ],
        },
        _tool_msg("call_1", "real"),
        _tool_msg("call_1", CANCELLED_TOOL_OUTPUT),
    ]
    assert message_history._tool_pairs_need_repair() is True
    message_history.normalize_tool_pairs()
    assert message_history._tool_pairs_need_repair() is False

    message_history.messages = [
        {"role": "user", "content": "hi"},
        _tool_msg("call_ghost", "orphan"),
    ]
    assert message_history._tool_pairs_need_repair() is True
    message_history.normalize_tool_pairs()
    assert message_history._tool_pairs_need_repair() is False


def test_set_messages_heals_poisoned_order(message_history):
    """Loading a session saved in the bad order repairs it before first use."""
    raw = _poisoned_history(message_history)

    message_history.set_messages([dict(m) for m in raw])

    roles = [m["role"] for m in message_history.messages]
    assert roles == ["system", "user", "assistant", "tool", "user", "assistant"]
    assert _outputs_per_call(message_history.messages) == {"call_1": 1}


def test_complete_chain_ending_in_tool_does_not_defer(message_history):
    """A turn that stopped without an assistant reply still has a CLOSED chain.

    Real user input must not be queued there (it would be missing from the
    next request entirely). Reached via guidance mode, an interrupted run or
    the /stop socket command.
    """
    message_history.messages = [
        {"role": "user", "content": "do it"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}}
            ],
        },
        _tool_msg("call_1", "done"),
    ]

    assert message_history.has_open_tool_chain() is False

    message_history.add_user_message("new user input")

    assert message_history.messages[-1]["content"] == "new user input"
    assert message_history._deferred_user_messages == []


def test_partially_answered_chain_still_defers(message_history):
    """Two calls, one result: the chain is open, so the message is queued."""
    message_history.messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        _tool_msg("call_1", "done"),
    ]

    assert message_history.has_open_tool_chain() is True

    message_history.add_user_message("queued")

    assert message_history._deferred_user_messages == [
        {"role": "user", "content": "queued"}
    ]
    assert not any(m.get("content") == "queued" for m in message_history.messages)


def test_plugin_nudge_after_tool_results_is_in_next_request(message_history):
    """reminder plugin: after_ai_processing(has_tool_calls=True) adds a nudge.

    It lands after the tool results of a closed chain and must be visible to
    the very next request (that is the whole point of the nudge).
    """
    message_history.messages = [
        {"role": "user", "content": "do it"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}}
            ],
        },
        _tool_msg("call_1", "done"),
    ]

    nudge = "<system-reminder>\nstop and check\n</system-reminder>"
    message_history.add_user_message(nudge)

    assert message_history.messages[-1]["content"] == nudge
    assert message_history.get_messages()[-1]["content"] == nudge


def test_ensure_flushes_deferred_after_placeholders(message_history):
    """Queued message must reach the request, after the placeholder output."""
    _add_tool_calls(message_history, ["call_1", "call_2"])
    message_history.add_user_message("queued mid chain")
    assert message_history._deferred_user_messages

    manager = _fake_session_manager(message_history)
    manager._ensure_tool_calls_have_responses()

    roles = [m["role"] for m in message_history.messages]
    assert roles == ["assistant", "tool", "tool", "user"]
    assert message_history._deferred_user_messages == []
    assert message_history.messages[-1]["content"] == "queued mid chain"


def test_orphan_tool_output_is_not_an_open_chain(message_history):
    """No owning assistant -> normalize drops it, so do not defer forever."""
    message_history.messages = [
        {"role": "user", "content": "hi"},
        _tool_msg("call_ghost", "orphan"),
    ]

    assert message_history.has_open_tool_chain() is False
