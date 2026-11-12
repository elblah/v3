"""Unit tests for the loop detector's repetition test."""

from aicoder.plugins.loop_detector import (
    MIN_REPEATS,
    NEEDLE_WORDS,
    _SEPARATORS,
    _repeats,
)


def words(text: str) -> list[str]:
    """Split text the same way the plugin does before calling _repeats."""
    return text.translate(_SEPARATORS).split()


def run(period: int) -> list[str]:
    """A leading intro followed by many copies of one period-word run."""
    unit = " ".join(f"tok{i}" for i in range(period))
    return words("intro " + (unit + " ") * 12)


def test_short_period_loop_trips():
    assert _repeats(run(13)) is True


def test_single_word_loop_trips():
    assert _repeats(run(1)) is True


def test_period_larger_than_needle_trips():
    # The repeating run must fit in the searched tail, so a run as long as
    # NEEDLE_WORDS is the largest one that still trips.
    assert _repeats(run(NEEDLE_WORDS)) is True


def test_too_short_to_trip():
    assert _repeats(words("one two three")) is False
    assert _repeats([]) is False


def test_two_copies_are_not_enough():
    unit = " ".join(f"tok{i}" for i in range(20))
    assert _repeats(words("intro " + unit * (MIN_REPEATS - 1))) is False


def test_scattered_repeat_is_not_a_loop():
    # The old rule (needle occurring MIN_REPEATS times anywhere in the window)
    # aborted these; they are legitimate structured output.
    unit = "path fill stroke width circle rect line"
    text = " ".join([unit, "alpha beta gamma delta", unit, "epsilon zeta", unit])
    assert _repeats(words(text)) is False


def test_svg_shapes_are_not_a_loop():
    svg = " ".join(
        f'<path d="M {i} L {i + 10} Z" fill="#fff" stroke="red" />'
        for i in range(6)
    )
    assert _repeats(words(svg)) is False


def test_css_rules_are_not_a_loop():
    css = " ".join(
        f".row-{i} {{ margin: 0; padding: 2px; color: #{i}{i}{i}; }}"
        for i in range(8)
    )
    assert _repeats(words(css)) is False


def test_json_rows_are_not_a_loop():
    rows = " ".join(
        f'{{"id": {i}, "name": "user{i}", "active": true}}' for i in range(8)
    )
    assert _repeats(words(rows)) is False


def test_plain_prose_is_not_a_loop():
    prose = (
        "The detector watches the live stream because stopping afterwards is "
        "useless when the tokens are already billed and the tool calls have "
        "already run on this machine without asking anybody first."
    )
    assert _repeats(words(prose)) is False
