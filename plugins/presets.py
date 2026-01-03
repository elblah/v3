"""
Presets plugin for AI Coder v3

Allows users to quickly switch between AI behavior presets (creative, balanced, stable, etc.)
and adjust individual parameters like temperature and top_p.

Features:
- Predefined presets with aliases
- Override/add presets via AICODER_PRESETS_JSON env var
- Set initial preset via AICODER_PRESET env var
- Modify individual parameters (switches to Custom mode)
- Commands: /preset, /preset list, /preset <name|number|alias>, /preset set <param> <value>

No changes to core required - modifies os.environ directly which Config reads.
"""

import os
import json
from typing import Dict, List, Optional, Any

from aicoder.core.config import Config


def create_plugin(ctx):
    """
    Presets plugin - manage AI behavior presets
    """

    # Default presets - only use widely-supported parameters to avoid API errors
    DEFAULT_PRESETS = [
        {
            "name": "Creative",
            "aliases": ["creative", "c", "cre"],
            "description": "Good for creative solutions, brainstorming, philosophical chat",
            "parameters": {
                "temperature": 1.0,
                "top_p": 0.95
            }
        },
        {
            "name": "Balanced",
            "aliases": ["balanced", "b", "norm", "normal"],
            "description": "Balanced mix of creativity and reliability for general use",
            "parameters": {
                "temperature": 0.7,
                "top_p": 0.9
            }
        },
        {
            "name": "Stable",
            "aliases": ["stable", "s", "precise", "strict"],
            "description": "Low creativity, highly deterministic - best for coding and precise tasks",
            "parameters": {
                "temperature": 0.0
            }
        },
        {
            "name": "Chat",
            "aliases": ["chat", "conversational", "conv"],
            "description": "Optimized for conversational responses and explanations",
            "parameters": {
                "temperature": 0.8,
                "top_p": 0.92
            }
        },
        {
            "name": "Code",
            "aliases": ["code", "coder", "dev"],
            "description": "Optimized for code generation and technical solutions",
            "parameters": {
                "temperature": 0.2
            }
        }
    ]

    # Runtime state (closure-based)
    presets: List[Dict] = []
    current_preset_name: str = "Custom"
    current_preset_original: str = ""
    active_parameters: Dict[str, Any] = {}

    # Colors from Config
    colors = Config.colors

    def print_color(color_name: str, text: str) -> None:
        """Print text with color"""
        color_code = colors.get(color_name, "")
        print(f"{color_code}{text}{colors['reset']}")

    def load_presets_from_env() -> None:
        """Load presets from AICODER_PRESETS_JSON env var"""
        nonlocal presets

        presets_json = os.environ.get("AICODER_PRESETS_JSON", "")
        if presets_json:
            try:
                loaded = json.loads(presets_json)
                if isinstance(loaded, list) and len(loaded) > 0:
                    presets = loaded
                    print_color("cyan", f"[+] Loaded {len(presets)} preset(s) from AICODER_PRESETS_JSON")
                    return
            except json.JSONDecodeError as e:
                print_color("yellow", f"[!] Failed to parse AICODER_PRESETS_JSON: {e}")
                print_color("yellow", "[!] Using default presets")

        # Use defaults
        presets = DEFAULT_PRESETS.copy()

    def get_preset_by_identifier(identifier: str) -> Optional[Dict]:
        """
        Find preset by name, alias, or number (1-indexed)
        Returns the preset dict or None
        """
        # Try number first
        try:
            num = int(identifier)
            if 1 <= num <= len(presets):
                return presets[num - 1]
        except ValueError:
            pass

        # Try name or alias (case-insensitive)
        identifier_lower = identifier.lower()

        for preset in presets:
            # Check name
            if preset["name"].lower() == identifier_lower:
                return preset

            # Check aliases
            aliases = preset.get("aliases", [])
            if identifier_lower in [a.lower() for a in aliases]:
                return preset

        return None

    def apply_parameters_to_env(parameters: Dict[str, Any]) -> None:
        """Apply parameters to environment variables (which Config reads)"""
        for key, value in parameters.items():
            env_key = key.upper()
            os.environ[env_key] = str(value)

    def apply_preset(name_or_number_or_alias: str) -> bool:
        """
        Apply a preset by name, number, or alias
        Returns True on success, False on failure
        """
        nonlocal current_preset_name, current_preset_original, active_parameters

        preset = get_preset_by_identifier(name_or_number_or_alias)
        if not preset:
            return False

        current_preset_name = preset["name"]
        current_preset_original = preset["name"]
        active_parameters = preset.get("parameters", {}).copy()

        # Apply to environment
        apply_parameters_to_env(active_parameters)

        return True

    def set_parameter(param_name: str, value: str) -> bool:
        """
        Set an individual parameter value (switches to Custom mode)
        Returns True on success, False on failure
        """
        nonlocal current_preset_name, active_parameters

        # Parse value
        try:
            # Try float
            parsed_value = float(value)
            # If it's a whole number, convert to int
            if parsed_value == int(parsed_value):
                parsed_value = int(parsed_value)
        except ValueError:
            print_color("yellow", f"[!] Invalid value for {param_name}: {value}")
            return False

        # Store original preset name if we're switching from a named preset
        if current_preset_name != "Custom":
            current_preset_original = current_preset_name
        current_preset_name = "Custom"

        # Update active parameters
        active_parameters[param_name.lower()] = parsed_value

        # Apply to environment
        apply_parameters_to_env({param_name.lower(): parsed_value})

        return True

    def get_current_preset_info() -> Dict[str, Any]:
        """Get information about the current preset"""
        if current_preset_name == "Custom" and current_preset_original:
            original_preset = get_preset_by_identifier(current_preset_original)
            original_description = original_preset.get("description", "") if original_preset else ""
        else:
            original_preset = get_preset_by_identifier(current_preset_name)
            original_description = original_preset.get("description", "") if original_preset else ""

        return {
            "name": current_preset_name,
            "original_name": current_preset_original,
            "description": original_preset.get("description", "") if original_preset else "",
            "parameters": active_parameters.copy(),
            "is_custom": current_preset_name == "Custom"
        }

    def format_parameters(parameters: Dict[str, Any], indent: str = "        ") -> str:
        """Format parameters dict for display"""
        lines = []
        for key, value in sorted(parameters.items()):
            # Format numeric values nicely
            if isinstance(value, float):
                formatted = f"{value:.2f}".rstrip('0').rstrip('.') if '.' in f"{value:.2f}" else str(value)
            else:
                formatted = str(value)
            lines.append(f"{indent}- {key}: {formatted}")
        return "\n".join(lines)

    def show_current_preset() -> None:
        """Show current preset information"""
        info = get_current_preset_info()

        print_color("brightGreen", f"[*] Current Profile: {info['name']}")
        if info['is_custom']:
            print_color("yellow", f"    (variables are in custom mode)")

        if info['description'] and not info['is_custom']:
            print(f"    {info['description']}")

        if info['parameters']:
            print(f"{colors['cyan']}    Values:{colors['reset']}")
            print(format_parameters(info['parameters']))

    def list_presets() -> None:
        """List all available presets"""
        info = get_current_preset_info()

        print_color("brightGreen", f"[*] Current Profile: {info['name']} ({presets.index(get_preset_by_identifier(info['original_name'])) + 1 if get_preset_by_identifier(info['original_name']) else '?'}")
        print()

        for idx, preset in enumerate(presets, 1):
            is_current = preset["name"] == info['original_name'] or preset["name"] == info['name']

            # Preset header
            prefix = colors['brightYellow'] if is_current else ""
            suffix = colors['reset'] if is_current else ""
            marker = "* " if is_current else "  "

            print(f"{prefix}{marker}{idx}) {preset['name']}: {preset['description']}{suffix}")

            # Aliases
            aliases = preset.get("aliases", [])
            if aliases:
                alias_str = ", ".join(aliases)
                print(f"        Aliases: {alias_str}")

            # Parameters
            parameters = preset.get("parameters", {})
            if parameters:
                print(f"{colors['cyan']}        Values:{colors['reset']}")
                print(format_parameters(parameters))

            print()

    def initialize_preset() -> None:
        """Initialize preset from AICODER_PRESET env var"""
        initial_preset = os.environ.get("AICODER_PRESET", "").strip()
        if initial_preset:
            if apply_preset(initial_preset):
                print_color("cyan", f"[+] Initial preset set to: {current_preset_name}")
            else:
                print_color("yellow", f"[!] Unknown preset: {initial_preset}")

    # Register command: /preset
    def cmd_preset(args: str) -> None:
        """Main /preset command handler"""
        args = args.strip()

        # Show current preset
        if not args:
            show_current_preset()
            return

        # List presets
        if args == "list":
            list_presets()
            return

        # Set individual parameter: /preset set <param> <value>
        parts = args.split()
        if len(parts) >= 2 and parts[0].lower() == "set":
            if len(parts) < 3:
                print_color("yellow", "[!] Usage: /preset set <parameter> <value>")
                print_color("yellow", "[!] Examples: /preset set temperature 0.3")
                print_color("yellow", "[!]           /preset set top_p 0.8")
                return

            param_name = parts[1]
            value = parts[2]

            if set_parameter(param_name, value):
                info = get_current_preset_info()
                desc = info['description'] if not info['is_custom'] else "(variables are in custom mode)"
                print_color("brightGreen", f"[*] Current Profile: Custom - {desc}")
                print(f"{colors['cyan']}        Values:{colors['reset']}")
                print(format_parameters(info['parameters']))
            return

        # Apply preset by name, alias, or number
        if apply_preset(args):
            info = get_current_preset_info()
            print_color("brightGreen", f"[*] Current Profile: {info['name']} - {info['description']}")
            print(f"{colors['cyan']}        Values:{colors['reset']}")
            print(format_parameters(info['parameters']))
        else:
            # Show helpful message
            print_color("yellow", f"[!] Unknown preset: {args}")
            print_color("cyan", "[i] Use /preset list to see available presets")

    # Register the command
    ctx.register_command(
        "preset",
        cmd_preset,
        "Manage AI behavior presets (creative, stable, code, etc.)"
    )

    # Initialize
    load_presets_from_env()
    initialize_preset()

    # No cleanup needed
    return {}
