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
        self.skills_dir = ".aicoder/skills"
        self.skills: dict = {}

    def discover_skills(self) -> int:
        """Discover all skills from skills directory"""
        if not os.path.exists(self.skills_dir):
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
            return "[SKILLS] No skills available."

        skills_list = []
        for skill_name, skill_info in sorted(self.skills.items()):
            skills_list.append(
                f"- {skill_name} ({skill_info['path']}): {skill_info['description']}"
            )

        return """[SKILLS] You have access to these skills. Load a skill by reading its SKILL.md file when the task requires it.

Available Skills:

""" + "\n".join(skills_list) + """

To load a skill, use: read_file(path/to/SKILL.md)
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
                return "No skills available in .aicoder/skills/"

            output = "Available Skills (AI can load these when needed):\n\n"
            for skill_name, skill_info in sorted(manager.skills.items()):
                output += f"  • {skill_name}\n"
                output += f"    {skill_info['description']}\n\n"

            output += f"Total: {len(manager.skills)} skill(s)\n"
            output += "\nUse /skills reload to update this list."
            return output

        if args[0] == "message":
            # Show raw [SKILLS] message from history
            for msg in ctx.app.message_history.messages:
                content = msg.get("content", "")
                if msg.get("role") == "user" and content.startswith("[SKILLS]"):
                    return content
            return "No [SKILLS] message found in history."

        if args[0] == "help":
            return """Skills Commands:

/skills          - Show available skills (user-friendly summary)
/skills message   - Show raw [SKILLS] message (what AI sees)
/skills reload   - Reload skills from disk (updates [SKILLS] message)

The [SKILLS] message is automatically maintained before each user prompt.
Skills are listed with their SKILL.md paths - use read_file() to load one.
"""

        if args[0] == "reload":
            old_count = len(manager.skills)
            new_count = manager.reload_skills()

            # Update [SKILLS] message immediately
            manager.ensure_skills_message(ctx.app.message_history)

            if new_count == old_count:
                return f"Skills reloaded. Found {new_count} skills (unchanged)."
            else:
                return f"Skills reloaded. Found {new_count} skills (was {old_count})."

        return f"Unknown command: {args[0]}. Use /skills help for usage."

    # Register hook
    ctx.register_hook("before_user_prompt", before_user_prompt)

    # Register command
    ctx.register_command("skills", handle_skills_command, description="Manage Claude Skills")

    print(f"[+] Skills plugin loaded ({count} skills found)")
    print("  - [SKILLS] message auto-maintained")
    print("  - /skills reload command")

    # Cleanup function
    def cleanup():
        manager.skills.clear()

    return {"cleanup": cleanup}
