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


def _orjson_dumps(obj):
    """orjson.dumps returns bytes, wrap to return str like json.dumps"""
    return orjson.dumps(obj).decode('utf-8')


def create_plugin(ctx):
    """Patch json module with orjson"""
    json.loads = orjson.loads
    json.dumps = _orjson_dumps

    if ctx.app and hasattr(ctx.app, 'Config') and ctx.app.Config.debug():
        print(f"[orjson] JSON speedups enabled ({orjson.__version__})")