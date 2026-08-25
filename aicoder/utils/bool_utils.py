"""Boolean string parsing shared across commands and env vars."""

import os

TRUTHY = frozenset(("1", "true", "t", "yes", "y", "on", "enable"))
FALSY = frozenset(("0", "false", "f", "no", "n", "off", "disable"))

_MISSING = object()


def parse_bool(value: str, default=_MISSING) -> bool:
    """Parse a string as boolean. Returns True/False.

    Accepts: 1/true/t/yes/y/on/enable and 0/false/f/no/n/off/disable
    (case-insensitive, whitespace-stripped).

    Raises ValueError on anything else, unless default is given.
    """
    v = value.strip().lower()
    if v in TRUTHY:
        return True
    if v in FALSY:
        return False
    if default is not _MISSING:
        return default
    raise ValueError(
        f"unrecognized boolean value: {value!r} "
        f"(expected one of: {', '.join(sorted(TRUTHY | FALSY))})"
    )


def env_bool(name: str, default: bool = False) -> bool:
    """Read an env var as boolean. Unset or empty -> default, else parse_bool."""
    value = os.environ.get(name)
    if not value:
        return default
    return parse_bool(value)
