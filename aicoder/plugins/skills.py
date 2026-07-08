"""
Claude Skills Plugin - Simple and Spec-Compliant

- Auto-discovery of skills from .aicoder/skills/ and ~/.config/aicoder-v3/skills/
- Local skills override global on name collision
- SKILL.md parsing with YAML frontmatter (per spec)
- Skills list baked into system prompt at session start via on_system_prompt_append
- AI loads skills via read_file() when needed
- AI runs scripts via run_shell_command() when needed

Commands:
- /skills - Show available skills
"""

import os

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
                yaml_lines = yaml_text.split('\n')
                line_idx = yaml_lines.index(line)
                for next_line in yaml_lines[line_idx + 1:]:
                    if next_line.startswith(' '):
                        desc_lines.append(next_line.strip())
                    elif next_line.strip() == '':
                        continue
                    else:
                        break
                frontmatter[key] = ' '.join(desc_lines)
            else:
                frontmatter[key] = value

    return frontmatter


class SkillsManager:
    """Skills management"""

    def __init__(self):
        self.skills_dirs: list = []
        self.skills: dict = {}

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

        if not self.skills_dirs:
            return 0

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
                        self.skills[name] = {
                            "name": name,
                            "path": os.path.join(skill_path, "SKILL.md"),
                            "description": description,
                            "source": source,
                        }
                        count += 1
                except Exception:
                    continue

        return count

    def generate_skills_text(self) -> str:
        """Generate skills section for system prompt"""
        if not self.skills:
            return ""

        lines = []
        for skill_name, skill_info in sorted(self.skills.items()):
            lines.append(
                f"- {skill_name} ({skill_info['path']}): {skill_info['description']}"
            )

        dirs_display = ", ".join(d for _, d in self.skills_dirs)

        return (
            "<skills>\n"
            "Available skills (informational only - load when needed via read_file):\n"
            "\n"
            + "\n".join(lines)
            + f"\n\nLoading from: {dirs_display} ({len(self.skills)} skills found)\n"
            "</skills>"
        )


def create_plugin(ctx):
    """Skills plugin - Simple YAGNI implementation"""

    manager = SkillsManager()
    count = manager.discover_skills()

    def handle_skills_command(args_str: str) -> str:
        """Handle /skills command"""
        args = args_str.strip().split(maxsplit=1) if args_str.strip() else []

        if not args:
            if not manager.skills:
                if manager.skills_dirs:
                    dirs_str = ", ".join(d for _, d in manager.skills_dirs)
                    return f"No skills available in {dirs_str}"
                return "No skills directory found (.aicoder/skills or ~/.config/aicoder-v3/skills)"

            dirs_display = ", ".join(d for _, d in manager.skills_dirs)

            output = f"Available Skills (loading from {dirs_display}):\n\n"
            for skill_name, skill_info in sorted(manager.skills.items()):
                source = skill_info.get("source", "unknown")
                output += f"  \u2022 {skill_name} [{source}]\n"
                output += f"    {skill_info['description']}\n\n"

            output += f"Total: {len(manager.skills)} skill(s)"
            return output

        if args[0] == "help":
            return """Skills Commands:

/skills       - Show available skills
/skills help  - Show this help

Skills are discovered at session start from:
  ~/.config/aicoder-v3/skills/ (global)
  .aicoder/skills/ (local)
Local skills override global on name collision."""

        return f"Unknown command: {args[0]}. Use /skills help for usage."

    def on_system_prompt_append():
        return manager.generate_skills_text()

    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)
    ctx.register_command("skills", handle_skills_command, description="List available skills")

    if Config.debug():
        if count > 0:
            dirs_display = ", ".join(d for _, d in manager.skills_dirs)
            LogUtils.print(f"[+] Skills plugin loaded ({count} skills found)")
            LogUtils.print(f"  - Loading from: {dirs_display}")
        else:
            LogUtils.print("[+] Skills plugin loaded (0 skills found)")

    def cleanup():
        manager.skills.clear()

    return {"cleanup": cleanup}
