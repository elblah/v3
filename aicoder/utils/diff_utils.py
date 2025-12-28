"""
Diff utilities for generating file differences

"""

from aicoder.utils.shell_utils import execute_command_sync
from aicoder.core.config import Config


def colorize_diff(diff_output: str) -> str:
    """Colorize diff output"""
    lines = diff_output.split("\n")
    colored_lines = []

    for line in lines:
        # Skip diff header lines (--- and +++)
        if line.startswith("---") or line.startswith("+++"):
            continue

        # Color code based on diff line type
        if line.startswith("-"):
            colored_lines.append(
                f"{Config.colors['red']}{line}{Config.colors['reset']}"
            )
        elif line.startswith("+"):
            colored_lines.append(
                f"{Config.colors['green']}{line}{Config.colors['reset']}"
            )
        elif line.startswith("@@"):
            colored_lines.append(
                f"{Config.colors['cyan']}{line}{Config.colors['reset']}"
            )
        else:
            colored_lines.append(line)

    return "\n".join(colored_lines)


def generate_unified_diff(old_path: str, new_path: str) -> str:
    """Generate unified diff between two files"""
    result = execute_command_sync(f'diff -u "{old_path}" "{new_path}"')

    if result.success:
        return result.stdout or "No changes - content is identical"
    elif result.exit_code == 1:
        # diff returns 1 when differences are found
        return result.stdout or "Differences found (no output)"
    else:
        return f"Error generating diff: {result.stderr}"


def generate_unified_diff_with_status(old_path: str, new_path: str) -> dict:
    """Generate unified diff and return whether changes were detected"""
    result = execute_command_sync(f'diff -u "{old_path}" "{new_path}"')

    if result.success:
        # No differences found (exit code 0)
        return {
            "has_changes": False,
            "diff": result.stdout or "No changes - content is identical",
            "exit_code": 0,
        }
    elif result.exit_code == 1:
        # Differences found (exit code 1 is normal for diff)
        return {
            "has_changes": True,
            "diff": result.stdout or "Differences found (no output)",
            "exit_code": 1,
        }
    else:
        # Error occurred
        return {
            "has_changes": False,
            "diff": f"Error generating diff: {result.stderr}",
            "exit_code": result.exit_code,
        }
