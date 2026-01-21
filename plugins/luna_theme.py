"""
Luna Theme Plugin - Simple Luna color palette

A minimal theme plugin that applies the Luna color scheme.
Just the Luna colors, nothing fancy.

Colors:
- Soft pink/magenta tones for red
- Fresh green for green
- Golden yellow for yellow
- True sky blue for blue
- Cyan for cyan
- Pure white for white
"""

def create_plugin(ctx):
    """Apply Luna theme colors"""

    # Luna color palette (exact RGB values from theme.py)
    # Config.colors is used throughout the codebase
    from aicoder.core.config import Config
    from aicoder.utils.log import LogUtils

    # Update color codes (using \x1b for consistency)
    # Using distinct colors for proper semantic differentiation
    Config.colors["red"] = "\x1b[38;2;255;120;180m"           # Soft Pink/Magenta (#FF78B4)
    Config.colors["green"] = "\x1b[38;2;120;255;120m"          # Fresh Green (#78FF78)
    Config.colors["yellow"] = "\x1b[38;2;255;220;100m"         # Golden Yellow (#FFDC64)
    Config.colors["blue"] = "\x1b[38;2;100;180;255m"           # Sky Blue (#64B4FF)
    Config.colors["magenta"] = "\x1b[38;2;255;120;200m"        # Pink/Magenta (#FF78C8)
    Config.colors["cyan"] = "\x1b[38;2;100;220;220m"           # Cyan (#64DCDC)
    Config.colors["white"] = "\x1b[38;2;255;255;255m"          # Pure White (#FFFFFF)

    # Update bright variants (Config uses camelCase: brightGreen, brightRed, etc.)
    Config.colors["brightGreen"] = "\x1b[38;2;150;255;150m"   # Brighter Green
    Config.colors["brightRed"] = "\x1b[38;2;255;150;200m"     # Brighter Pink
    Config.colors["brightYellow"] = "\x1b[38;2;255;240;120m"  # Brighter Yellow
    Config.colors["brightBlue"] = "\x1b[38;2;120;200;255m"    # Brighter Sky Blue
    Config.colors["brightMagenta"] = "\x1b[38;2;255;150;220m" # Brighter Pink
    Config.colors["brightCyan"] = "\x1b[38;2;120;240;240m"    # Brighter Cyan
    Config.colors["brightWhite"] = "\x1b[38;2;255;255;255m"   # Pure White

    if Config.debug():
        LogUtils.print("  - Luna theme applied")
