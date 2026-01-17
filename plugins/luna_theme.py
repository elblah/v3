"""
Luna Theme Plugin - Simple Luna color palette

A minimal theme plugin that applies the Luna color scheme.
Just the Luna colors, nothing fancy.

Colors:
- Soft pink/magenta tones for red
- Lime green for green
- Gold for yellow
- Light cyan for blue/cyan
- Pure white for white
"""

def create_plugin(ctx):
    """Apply Luna theme colors"""

    # Luna color palette (exact RGB values from theme.py)
    # Config.colors is used throughout the codebase
    from aicoder.core.config import Config

    # Update color codes (using \x1b for consistency)
    Config.colors["red"] = "\x1b[38;2;255;175;255m"           # Light Pink/Magenta (#FFAFFF)
    Config.colors["green"] = "\x1b[38;2;215;255;95m"          # Lime Green (#D7FF5F)
    Config.colors["yellow"] = "\x1b[38;2;255;215;0m"           # Gold (#FFD700)
    Config.colors["blue"] = "\x1b[38;2;175;255;255m"           # Light Cyan (#AFFFFF)
    Config.colors["magenta"] = "\x1b[38;2;255;175;255m"        # Light Pink/Magenta (#FFAFFF)
    Config.colors["cyan"] = "\x1b[38;2;175;255;255m"           # Light Cyan (#AFFFFF)
    Config.colors["white"] = "\x1b[38;2;255;255;255m"          # Pure White (#FFFFFF)

    # Update bright variants (Config uses camelCase: brightGreen, brightRed, etc.)
    Config.colors["brightGreen"] = "\x1b[38;2;200;255;120m"   # Brighter Lime Green
    Config.colors["brightRed"] = "\x1b[38;2;255;200;255m"     # Brighter Magenta
    Config.colors["brightYellow"] = "\x1b[38;2;255;235;50m"   # Brighter Gold
    Config.colors["brightBlue"] = "\x1b[38;2;150;255;255m"    # Brighter Cyan
    Config.colors["brightMagenta"] = "\x1b[38;2;255;200;255m" # Brighter Magenta
    Config.colors["brightCyan"] = "\x1b[38;2;150;255;255m"    # Brighter Cyan
    Config.colors["brightWhite"] = "\x1b[38;2;255;255;255m"   # Pure White

    if Config.debug():
        print("  - Luna theme applied")
