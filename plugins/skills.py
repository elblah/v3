"""
Claude Skills Plugin - Simple and Spec-Compliant

Design: YAGNI - minimal, focused, no tools needed
- Auto-discovery of skills from .aicoder/skills/
- SKILL.md parsing with YAML frontmatter (per spec)
- Progressive disclosure via [SKILLS] message injection
- AI loads skills via read_file() when needed
- AI runs scripts via run_shell_command() when needed

Commands:
- /skills reload - Reload skills from disk (updates [SKILLS] message)
"""

import os
import re
from pathlib import Path
from typing import Optional

from aicoder.core.config import Config


def _parse_yaml_frontmatter(text: str) -> dict:
    """
    Parse YAML frontmatter from SKILL.md file
    Format:
    ---
    name: skill-name
    description: A description
    ---
    """
    parts = text.split('---', 2)

    if len(parts) < 3:
        return {}

    frontmatter = {}
    for line in parts[1].strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip()] = value.strip()

    return frontmatter


class SkillsManager:
    """Skills management - all state in closure"""

    def __init__(self):
        self.skills_dir = None
        self.skills_source = None
        self.skills: dict = {}

    def get_skills_directory(self) -> Optional[str]:
        """
        Get skills directory - exclusive: local OR global, never both
        
        Priority order:
        1. Local .aicoder/skills (if exists) - project-specific takes precedence
        2. Global ~/.config/aicoder-v3/skills (fallback)
        """
        local_dir = os.path.join(os.getcwd(), ".aicoder/skills")
        global_dir = os.path.expanduser("~/.config/aicoder-v3/skills")
        
        if os.path.exists(local_dir):
            return local_dir
        elif os.path.exists(global_dir):
            return global_dir
        return None

    def get_skills_source(self) -> Optional[str]:
        """Return 'local', 'global', or None"""
        if not self.skills_dir:
            return None
        if self.skills_dir.endswith(".aicoder/skills"):
            return "local"
        elif self.skills_dir.endswith("skills") and "aicoder-v3" in self.skills_dir:
            return "global"
        return "unknown"

    def discover_skills(self) -> int:
        """Discover all skills from skills directory"""
        self.skills_dir = self.get_skills_directory()
        self.skills_source = self.get_skills_source()
        
        if not self.skills_dir:
            return 0

        count = 0
        for skill_name in os.listdir(self.skills_dir):
            skill_path = os.path.join(self.skills_dir, skill_name)

            if not os.path.isdir(skill_path):
                continue

            skill_md = os.path.join(skill_path, "SKILL.md")
            if not os.path.exists(skill_md):
                continue

            try:
                with open(skill_md, 'r', encoding='utf-8') as f:
                    content = f.read()

                frontmatter = _parse_yaml_frontmatter(content)
                name = frontmatter.get("name")
                description = frontmatter.get("description")

                if name and description:
                    # Relative path from project root
                    rel_path = os.path.join(self.skills_dir, skill_name, "SKILL.md")
                    self.skills[name] = {
                        "name": name,
                        "path": rel_path,
                        "description": description
                    }
                    count += 1
            except Exception:
                continue

        return count

    def generate_skills_message(self) -> str:
        """Generate [SKILLS] message with available skills"""
        if not self.skills:
            if self.skills_dir:
                return f"[SKILLS] No skills available in {self.skills_dir}."
            else:
                return "[SKILLS] No skills available (no skills directory found)."

        skills_list = []
        for skill_name, skill_info in sorted(self.skills.items()):
            # Use relative path for cleaner display
            display_path = skill_info['path']
            if self.skills_source == "global" and display_path.startswith(os.path.expanduser("~/.config/aicoder-v3/skills/")):
                display_path = display_path[len(os.path.expanduser("~/.config/aicoder-v3/skills/")):]
            elif self.skills_source == "local" and display_path.startswith(".aicoder/skills/"):
                display_path = display_path[len(".aicoder/skills/"):]
            
            skills_list.append(
                f"- {skill_name} ({display_path}): {skill_info['description']}"
            )

        source_info = ""
        if self.skills_dir:
            source_info = f"\nLoading from: {self.skills_dir} ({len(self.skills)} skills found)\n"

        return """[SKILLS] Available skills (informational only - load when the user requests it or when the scenario clearly requires it):
""" + source_info + """
Skills:

""" + "\n".join(skills_list) + """

To load a skill when needed, use: read_file(path/to/SKILL.md)
"""

    def ensure_skills_message(self, message_history) -> None:
        """
        Ensure [SKILLS] message exists in history
        - Replaces existing [SKILLS] message
        - Adds new one if missing
        """
        skills_text = self.generate_skills_message()

        # Find and replace existing [SKILLS] message
        for idx, msg in enumerate(message_history.messages):
            content = msg.get("content", "")
            if msg.get("role") == "user" and content.startswith("[SKILLS]"):
                message_history.messages[idx]["content"] = skills_text
                return

        # Add if missing (after system message at index 0, before first user message)
        insert_idx = 1
        message_history.messages.insert(insert_idx, {
            "role": "user",
            "content": skills_text
        })

    def reload_skills(self) -> int:
        """Reload skills from disk"""
        self.skills.clear()
        return self.discover_skills()


def create_plugin(ctx):
    """Skills plugin - Simple YAGNI implementation"""

    # Manager instance in closure
    manager = SkillsManager()

    # Discover skills on load
    count = manager.discover_skills()

    def before_user_prompt():
        """Hook: ensure [SKILLS] message exists before each user prompt"""
        manager.ensure_skills_message(ctx.app.message_history)

    # Command: /skills reload
    def handle_skills_command(args_str: str) -> str:
        """Handle /skills commands"""
        args = args_str.strip().split(maxsplit=1) if args_str.strip() else []

        if not args:
            # Show user-friendly summary
            if not manager.skills:
                if manager.skills_dir:
                    return f"No skills available in {manager.skills_dir}"
                else:
                    return "No skills directory found (.aicoder/skills or ~/.config/aicoder-v3/skills)"

            # Show source directory
            source_display = ""
            if manager.skills_source == "local":
                source_display = ".aicoder/skills"
            elif manager.skills_source == "global":
                source_display = os.path.expanduser("~/.config/aicoder-v3/skills")
            
            output = f"Available Skills (loading from {source_display}):\n\n"
            for skill_name, skill_info in sorted(manager.skills.items()):
                output += f"  • {skill_name}\n"
                output += f"    {skill_info['description']}\n\n"

            output += f"Total: {len(manager.skills)} skill(s)\n"
            output += "\nUse /skills reload to refresh this list."
            return output

        

        if args[0] == "help":
            help_text = """Skills Commands:

/skills          - Show available skills (user-friendly summary)
/skills reload   - Reload skills from disk (updates [SKILLS] message)
/skills help     - Show this help

The [SKILLS] message is automatically maintained before each user prompt.
Skills are loaded from either .aicoder/skills (local) or ~/.config/aicoder-v3/skills (global), never both.
"""
            
            # Add source info to help
            if manager.skills_dir:
                if manager.skills_source == "global":
                    help_text += f"\nCurrently loading from: ~/.config/aicoder-v3/skills\n"
                else:
                    help_text += f"\nCurrently loading from: .aicoder/skills\n"
            else:
                help_text += "\nNo skills directory found.\n"
                
            return help_text

        if args[0] == "reload":
            old_count = len(manager.skills)
            new_count = manager.reload_skills()

            # Update [SKILLS] message immediately
            manager.ensure_skills_message(ctx.app.message_history)

            # Show source in reload message
            source_display = ""
            if manager.skills_dir:
                if manager.skills_source == "global":
                    source_display = " from ~/.config/aicoder-v3/skills"
                else:
                    source_display = " from .aicoder/skills"

            if new_count == old_count:
                return f"Skills reloaded. Found {new_count} skills{source_display} (unchanged)."
            else:
                return f"Skills reloaded. Found {new_count} skills{source_display} (was {old_count})."

        return f"Unknown command: {args[0]}. Use /skills help for usage."

    # Register hook
    ctx.register_hook("before_user_prompt", before_user_prompt)

    # Register command
    ctx.register_command("skills", handle_skills_command, description="Manage Claude Skills")

    if Config.debug():
        if count > 0:
            source_display = manager.skills_dir
            if manager.skills_source == "global":
                # Show shortened path for global
                source_display = "~/.config/aicoder-v3/skills"

            print(f"[+] Skills plugin loaded ({count} skills found)")
            print(f"  - Loading from: {source_display}")
        else:
            print("[+] Skills plugin loaded (0 skills found)")
            print("  - No skills directory found")

        print("  - [SKILLS] message auto-maintained")
        print("  - /skills reload command")

    # Cleanup function
    def cleanup():
        manager.skills.clear()

    return {"cleanup": cleanup}
