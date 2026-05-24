#!/usr/bin/env python3
"""
orjson plugin - replaces stdlib json with orjson for faster parsing

Provides ~5x speedup on JSON parse, ~9x on encode

Requires: orjson package
Install: pip install orjson
"""

import sys

# Check orjson availability
try:
    import orjson
except ImportError:
    print("ERROR: orjson plugin requires 'orjson' package")
    print("Install with: pip install orjson")
    sys.exit(1)

import json


# Save original json.loads/dumps before patching
_original_json_loads = json.loads
_original_json_load = json.load
_original_json_dumps = json.dumps


def _orjson_loads(s, **kwargs):
    """Wrap orjson.loads to handle kwargs (fall back to stdlib if needed)"""
    if kwargs:
        return _original_json_loads(s, **kwargs)
    return orjson.loads(s)


def _orjson_load(f, **kwargs):
    """Wrap json.load to handle kwargs (fall back to stdlib if needed)"""
    if kwargs:
        return _original_json_load(f, **kwargs)
    return orjson.loads(f.read())


def _orjson_dumps(obj, **kwargs):
    """orjson.dumps returns bytes, wrap to return str like json.dumps"""
    # Handle separators=(',', ':') - orjson uses OPT_INDENT_2 etc
    if 'separators' in kwargs:
        # Fall back to original stdlib json for compact formatting
        return _original_json_dumps(obj, **kwargs)
    return orjson.dumps(obj).decode('utf-8')


def create_plugin(ctx):
    """Patch json module with orjson"""
    json.loads = _orjson_loads
    json.load = _orjson_load
    json.dumps = _orjson_dumps

    if ctx.app and hasattr(ctx.app, 'Config') and ctx.app.Config.debug():
        print(f"[orjson] JSON speedups enabled ({orjson.__version__})")