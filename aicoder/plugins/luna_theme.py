"""
Luna Theme Plugin - Simple Luna color palette

A minimal theme plugin that applies the Luna color scheme.
Just the Luna colors, nothing fancy.

Colors:
- Light pink/magenta tones for red
- Lime green for green
- Gold for yellow
- Light cyan for blue/cyan
- Pure white for white

Detection:
- Uses true colors (24-bit) when not in screen
- Falls back to 256 palette when $STY is detected (running in screen)
"""

def create_plugin(ctx):
    """Apply Luna theme colors"""

    from aicoder.core.config import Config
    from aicoder.utils.log import LogUtils
    import sys
    import os

    # Check if output is piped or colors disabled
    if not sys.stdout.isatty() or os.environ.get('AICODER_DISABLE_COLORS') == '1':
        for key in Config.colors:
            Config.colors[key] = ""
        if Config.debug():
            reason = "colors disabled" if os.environ.get('AICODER_DISABLE_COLORS') == '1' else "piped output"
            LogUtils.print(f"  - Luna theme applied (no colors, {reason})")
        return

    # Detect if running inside screen - use 256 palette for screen sessions
    in_screen = os.environ.get('STY') is not None

    if in_screen:
        # 256 palette colors (for screen sessions)
        Config.colors["red"] = "\x1b[38;5;218m"        # Pink (#FFAAFF)
        Config.colors["green"] = "\x1b[38;5;191m"       # Lime (#D7FF5F)
        Config.colors["yellow"] = "\x1b[38;5;220m"      # Gold (#FFD700)
        Config.colors["blue"] = "\x1b[38;5;87m"         # Cyan (#AFFFFF)
        Config.colors["magenta"] = "\x1b[38;5;218m"    # Pink
        Config.colors["cyan"] = "\x1b[38;5;87m"         # Cyan
        Config.colors["white"] = "\x1b[38;5;231m"       # White (#FFFFFF)

        # Bright variants (256 palette)
        Config.colors["brightGreen"] = "\x1b[38;5;82m"  # Bright Lime
        Config.colors["brightRed"] = "\x1b[38;5;213m"   # Bright Pink
        Config.colors["brightYellow"] = "\x1b[38;5;226m" # Bright Gold
        Config.colors["brightBlue"] = "\x1b[38;5;123m"  # Bright Cyan
        Config.colors["brightMagenta"] = "\x1b[38;5;213m"
        Config.colors["brightCyan"] = "\x1b[38;5;123m"
        Config.colors["brightWhite"] = "\x1b[38;5;231m"

        if Config.debug():
            LogUtils.print("  - Luna theme applied (256 palette, screen detected)")
    else:
        # True color (24-bit) - original Luna theme colors
        Config.colors["red"] = "\x1b[38;2;255;175;255m"           # Light Pink/Magenta (#FFAFFF)
        Config.colors["green"] = "\x1b[38;2;215;255;95m"          # Lime Green (#D7FF5F)
        Config.colors["yellow"] = "\x1b[38;2;255;215;0m"          # Gold (#FFD700)
        Config.colors["blue"] = "\x1b[38;2;175;255;255m"          # Light Cyan (#AFFFFF)
        Config.colors["magenta"] = "\x1b[38;2;255;175;255m"       # Light Pink/Magenta (#FFAFFF)
        Config.colors["cyan"] = "\x1b[38;2;175;255;255m"           # Light Cyan (#AFFFFF)
        Config.colors["white"] = "\x1b[38;2;255;255;255m"         # Pure White (#FFFFFF)

        # Bright variants (true color)
        Config.colors["brightGreen"] = "\x1b[38;2;200;255;120m"   # Brighter Lime Green
        Config.colors["brightRed"] = "\x1b[38;2;255;200;255m"     # Brighter Magenta
        Config.colors["brightYellow"] = "\x1b[38;2;255;235;50m"   # Brighter Gold
        Config.colors["brightBlue"] = "\x1b[38;2;150;255;255m"    # Brighter Cyan
        Config.colors["brightMagenta"] = "\x1b[38;2;255;200;255m"
        Config.colors["brightCyan"] = "\x1b[38;2;150;255;255m"
        Config.colors["brightWhite"] = "\x1b[38;2;255;255;255m"

        if Config.debug():
            LogUtils.print("  - Luna theme applied (true color)")
