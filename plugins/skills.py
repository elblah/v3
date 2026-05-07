"""
Claude Skills Plugin - Simple and Spec-Compliant

Design: YAGNI - minimal, focused, no tools needed
- Auto-discovery of skills from .aicoder/skills/ and ~/.config/aicoder-v3/skills/
- Local skills override global on name collision
- SKILL.md parsing with YAML frontmatter (per spec)
- Progressive disclosure via [SKILLS] message injection
- AI loads skills via read_file() when needed
- AI runs scripts via run_shell_command() when needed

Commands:
- /skills reload - Reload skills from disk (updates [SKILLS] message)
"""

import os
from typing import Optional

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def _parse_yaml_frontmatter(text: str) -> dict:
    """
    Parse YAML frontmatter from SKILL.md file.
    Handles folded scalars (>) for multiline descriptions.
    """
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}

    frontmatter = {}
    yaml_text = parts[1].strip()
    
    for line in yaml_text.split('\n'):
        if line.strip().startswith('#'):
            continue
        
        if line.strip() == '---':
            break
        
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            if key == 'description' and value.startswith('>'):
                # Folded scalar - collect indented lines
                desc_lines = []
                # Find index of this line, collect following indented lines
                yaml_lines = yaml_text.split('\n')
                line_idx = yaml_lines.index(line)
                for next_line in yaml_lines[line_idx + 1:]:
                    if next_line.startswith(' '):
                        desc_lines.append(next_line.strip())
                    elif next_line.strip() == '':
                        continue  # skip blank
                    else:
                        break
                frontmatter[key] = ' '.join(desc_lines)
            else:
                frontmatter[key] = value
    
    return frontmatter


class SkillsManager:
    """Skills management - all state in closure"""

    def __init__(self):
        self.skills_dirs: list = []  # list of dirs that were scanned
        self.skills: dict = {}
        self._dir_mtimes: dict = {}  # dir_path -> mtime cache
        self._skill_mtimes: dict = {}  # skill_md_path -> mtime cache

    def _needs_rediscovery(self) -> bool:
        """Check if any skills directory or SKILL.md has changed since last scan"""
        # New dirs appeared or existing dirs changed
        current_dirs = self._get_dirs()
        if [(s, d) for s, d in current_dirs] != [(s, d) for s, d in self.skills_dirs]:
            return True
        for _, d in self.skills_dirs:
            try:
                if self._dir_mtimes.get(d) != os.path.getmtime(d):
                    return True
            except Exception:
                return True
        # Check individual SKILL.md files (catches edits to existing skills + deletions)
        for skill_info in self.skills.values():
            try:
                if self._skill_mtimes.get(skill_info['path']) != os.path.getmtime(skill_info['path']):
                    return True
            except Exception:
                return True  # file deleted
        return False

    @staticmethod
    def _get_dirs() -> list:
        """Get skills directories in scan order (global first, local second for override)"""
        global_dir = os.path.expanduser("~/.config/aicoder-v3/skills")
        local_dir = os.path.join(os.getcwd(), ".aicoder/skills")
        dirs = []
        if os.path.exists(global_dir):
            dirs.append(("global", global_dir))
        if os.path.exists(local_dir):
            dirs.append(("local", local_dir))
        return dirs

    def discover_skills(self) -> int:
        """Discover all skills from global then local dirs (local overrides on collision)"""
        self.skills_dirs = self._get_dirs()
        self.skills.clear()
        self._dir_mtimes.clear()
        self._skill_mtimes.clear()

        if not self.skills_dirs:
            return 0

        for _, d in self.skills_dirs:
            try:
                self._dir_mtimes[d] = os.path.getmtime(d)
            except Exception:
                pass

        count = 0
        for source, skills_dir in self.skills_dirs:
            for skill_name in os.listdir(skills_dir):
                skill_path = os.path.join(skills_dir, skill_name)

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
                        skill_md_path = os.path.join(skill_path, "SKILL.md")
                        self.skills[name] = {
                            "name": name,
                            "path": skill_md_path,
                            "description": description,
                            "source": source,
                        }
                        try:
                            self._skill_mtimes[skill_md_path] = os.path.getmtime(skill_md_path)
                        except Exception:
                            pass
                        count += 1
                except Exception:
                    continue

        return count

    def generate_skills_message(self) -> str:
        """Generate [SKILLS] message with available skills"""
        if not self.skills:
            if self.skills_dirs:
                dirs_str = ", ".join(d for _, d in self.skills_dirs)
                return f"[SKILLS] No skills available in {dirs_str}."
            else:
                return "[SKILLS] No skills available (no skills directory found)."

        skills_list = []
        for skill_name, skill_info in sorted(self.skills.items()):
            display_path = skill_info['path']
            source = skill_info.get("source", "unknown")
            if source == "global":
                prefix = os.path.expanduser("~/.config/aicoder-v3/skills/")
                if display_path.startswith(prefix):
                    display_path = display_path[len(prefix):]
            elif source == "local":
                prefix = os.path.join(os.getcwd(), ".aicoder/skills/")
                if display_path.startswith(prefix):
                    display_path = display_path[len(prefix):]

            skills_list.append(
                f"- {skill_name} ({source}/{display_path}): {skill_info['description']}"
            )

        source_info = ""
        if self.skills_dirs:
            dirs_display = ", ".join(d for _, d in self.skills_dirs)
            source_info = f"\nLoading from: {dirs_display} ({len(self.skills)} skills found)\n"

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
        from aicoder.core.message_history import MessageHistory

        skills_text = self.generate_skills_message()

        # Find and replace existing [SKILLS] message
        for idx, msg in enumerate(message_history.messages):
            content = MessageHistory._get_content_as_string(msg.get("content", ""))
            if msg.get("role") == "user" and content and content.startswith("[SKILLS]"):
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
        return self.discover_skills()


def create_plugin(ctx):
    """Skills plugin - Simple YAGNI implementation"""

    # Manager instance in closure
    manager = SkillsManager()

    # Discover skills on load
    count = manager.discover_skills()

    def before_user_prompt():
        """Hook: check for skill changes and ensure [SKILLS] message exists"""
        if manager._needs_rediscovery():
            old_count = len(manager.skills)
            manager.discover_skills()
            new_count = len(manager.skills)
            if new_count != old_count:
                LogUtils.print(f"[i] Skills updated ({old_count} → {new_count})")
            else:
                LogUtils.print("[i] Skills updated")
        manager.ensure_skills_message(ctx.app.message_history)

    # Command: /skills reload
    def handle_skills_command(args_str: str) -> str:
        """Handle /skills commands"""
        args = args_str.strip().split(maxsplit=1) if args_str.strip() else []

        if not args:
            # Show user-friendly summary
            if not manager.skills:
                if manager.skills_dirs:
                    dirs_str = ", ".join(d for _, d in manager.skills_dirs)
                    return f"No skills available in {dirs_str}"
                else:
                    return "No skills directory found (.aicoder/skills or ~/.config/aicoder-v3/skills)"

            dirs_display = ", ".join(d for _, d in manager.skills_dirs)

            output = f"Available Skills (loading from {dirs_display}):\n\n"
            for skill_name, skill_info in sorted(manager.skills.items()):
                source = skill_info.get("source", "unknown")
                output += f"  • {skill_name} [{source}]\n"
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
Skills are loaded from both ~/.config/aicoder-v3/skills (global) and .aicoder/skills (local).
Local skills override global on name collision.
"""
            
            if manager.skills_dirs:
                for source, d in manager.skills_dirs:
                    short = "~/.config/aicoder-v3/skills" if source == "global" else ".aicoder/skills"
                    help_text += f"\nCurrently loading from: {short}"
                help_text += "\n"
            else:
                help_text += "\nNo skills directory found.\n"
                
            return help_text

        if args[0] == "reload":
            old_count = len(manager.skills)
            new_count = manager.reload_skills()

            # Update [SKILLS] message immediately
            manager.ensure_skills_message(ctx.app.message_history)

            dirs_display = ""
            if manager.skills_dirs:
                parts = []
                for source, d in manager.skills_dirs:
                    short = "~/.config/aicoder-v3/skills" if source == "global" else ".aicoder/skills"
                    parts.append(short)
                dirs_display = " from " + " + ".join(parts)

            if new_count == old_count:
                return f"Skills reloaded. Found {new_count} skills{dirs_display} (unchanged)."
            else:
                return f"Skills reloaded. Found {new_count} skills{dirs_display} (was {old_count})."

        return f"Unknown command: {args[0]}. Use /skills help for usage."

    # Register hook
    ctx.register_hook("before_user_prompt", before_user_prompt)

    # Register command
    ctx.register_command("skills", handle_skills_command, description="Manage Claude Skills")

    if Config.debug():
        if count > 0:
            dirs_display = ", ".join(d for _, d in manager.skills_dirs)
            LogUtils.print(f"[+] Skills plugin loaded ({count} skills found)")
            LogUtils.print(f"  - Loading from: {dirs_display}")
        else:
            LogUtils.print("[+] Skills plugin loaded (0 skills found)")
            LogUtils.print("  - No skills directory found")

        LogUtils.print("  - [SKILLS] message auto-maintained")
        LogUtils.print("  - /skills reload command")

    # Cleanup function
    def cleanup():
        manager.skills.clear()

    return {"cleanup": cleanup}
