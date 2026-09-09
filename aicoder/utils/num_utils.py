"""Numeric tool-argument helpers.

Models emit JSON numbers that Python parses as float ("200.0") or numeric
strings. Tool args that must be integers go through coerce_int so the value
reaches subprocesses as a clean int.
"""


def coerce_int(value, name: str, default=None) -> int:
    """Coerce a tool argument to int.

    Accepts int, whole-number float, or numeric string ("7", "7.0").
    Returns default when value is None. Raises with a clear message otherwise.
    """
    if value is None:
        return default
    # bool is a subclass of int — reject it explicitly
    if isinstance(value, bool):
        raise Exception(f"{name} must be an integer, got: {value}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise Exception(f"{name} must be an integer, got: {value}")
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            try:
                number = float(text)
            except ValueError:
                raise Exception(f"{name} must be an integer, got: {value}")
            if number.is_integer():
                return int(number)
    raise Exception(f"{name} must be an integer, got: {value}")
