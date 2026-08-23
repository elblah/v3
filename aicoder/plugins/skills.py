"""
Skills Plugin

Auto-loads skills from skills/ dirs, discovers extras in skills-extra/ dirs.
See /skills help for details.
"""

import os

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Internal skills are virtual files served via read_file as /internal/<skill>/<file>
INTERNAL_PREFIX = "/internal/"


def _merge_internal_results(results) -> dict:
    """
    Merge on_internal_skills hook results into a single {name: skill} dict.

    First-wins in hook load order (local > global > bundled). Non-dict
    entries (None, garbage) at the outer level are skipped.
    """
    merged = {}
    if not results:
        return merged

    for result in results:
        if not isinstance(result, dict):
            continue
        for name, skill in result.items():
            if name not in merged and isinstance(skill, dict):
                merged[name] = skill

    return merged


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


def _get_skills(path: str, source: str) -> dict:
    """Scan a single skills dir, return {name: info} dict"""
    found = {}
    if not os.path.exists(path):
        return found
    for skill_name in os.listdir(path):
        skill_path = os.path.join(path, skill_name)
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
                found[name] = {
                    "name": name,
                    "path": os.path.join(skill_path, "SKILL.md"),
                    "description": description,
                    "source": source,
                }
        except Exception:
            continue
    return found


def _list_skill_dirs(base: str) -> list:
    """Return [(source_label, dir_path), ...] for skills/ and skills-extra/."""
    skill_path = os.path.join(base, "skills")
    extra_path = os.path.join(base, "skills-extra")
    result = []
    if os.path.exists(skill_path):
        result.append(("auto", skill_path))
    if os.path.exists(extra_path):
        result.append(("extra", extra_path))
    return result


class SkillsManager:
    """Skills management"""

    def __init__(self):
        self.skills: dict = {}
        self.extra_count: int = 0
        self._loaded_dirs: list = []

    def discover_skills(self) -> int:
        """Discover all skills. Local overrides global on name collision."""
        self.skills.clear()
        self.extra_count = 0
        self._loaded_dirs = []

        # Scan order: global auto, local auto (override), then count extras separately
        global_auto = _list_skill_dirs(os.path.expanduser("~/.config/aicoder-v3"))
        local_auto = _list_skill_dirs(os.path.join(os.getcwd(), ".aicoder"))

        loaded = 0
        for source, path in global_auto:
            if source == "auto":
                for name, info in _get_skills(path, "global").items():
                    self.skills[name] = info
                    loaded += 1
                self._loaded_dirs.append(path)
            else:
                self.extra_count += len(_get_skills(path, "global"))

        for source, path in local_auto:
            if source == "auto":
                for name, info in _get_skills(path, "local").items():
                    self.skills[name] = info
                    loaded += 1
                self._loaded_dirs.append(path)
            else:
                self.extra_count += len(_get_skills(path, "local"))

        return loaded

    def generate_skills_text(self, internal_skills: dict = None) -> str:
        """Generate skills section for system prompt"""
        if not self.skills and self.extra_count == 0 and not internal_skills:
            return ""

        lines = []
        for skill_name, skill_info in sorted(self.skills.items()):
            lines.append(
                f"- {skill_name} ({skill_info['path']}): {skill_info['description']}"
            )
        for name, skill in sorted((internal_skills or {}).items()):
            lines.append(
                f"- {name} ({INTERNAL_PREFIX}{name}/SKILL.md): {skill.get('description', '')}"
            )

        result = (
            "<skills>\n"
            "Available skills (informational only - load when needed via read_file):\n"
            "\n"
            "Note: To create/modify a skill, work in `.aicoder/skills/<name>/SKILL.md` "
            "(local project dir, writable). If modifying a global skill, copy its dir "
            "to `.aicoder/skills/` first, then edit the local copy. Global dir "
            "`~/.config/aicoder-v3/skills/` is READ-ONLY to the AI.\n"
            "\n"
            + "\n".join(lines)
        )

        if self.extra_count > 0:
            result += "\n\nAdditional skills (not auto-loaded, use read_file to load):"
            global_extra = os.path.join(os.path.expanduser("~/.config/aicoder-v3"), "skills-extra")
            local_extra = os.path.join(os.getcwd(), ".aicoder", "skills-extra")
            for label, path in [("global", global_extra), ("local", local_extra)]:
                skills = _get_skills(path, label)
                for name, info in sorted(skills.items()):
                    result += f"\n  - {name} ({info['path']})"

        result += "\n</skills>"
        return result

    def list_extra_skills(self) -> str:
        """Return human-readable listing of all extra skills."""
        parts = []
        global_extra = os.path.join(os.path.expanduser("~/.config/aicoder-v3"), "skills-extra")
        local_extra = os.path.join(os.getcwd(), ".aicoder", "skills-extra")

        for label, path in [("global", global_extra), ("local", local_extra)]:
            skills = _get_skills(path, label)
            if skills:
                parts.append(f"\n\n  [{label}]:")
                for name, info in sorted(skills.items()):
                    parts.append(f"\n\n    \u2022 {name}: {info['description']}")

        if not parts:
            return "No extra skills found."

        return "Extra Skills (not auto-loaded):" + "".join(parts)


def create_plugin(ctx):
    """Skills plugin"""

    manager = SkillsManager()
    count = manager.discover_skills()

    def internal_registry() -> dict:
        """Lazily query on_internal_skills hooks -> {name: {description, files}}.

        Fired on first need (prompt build, /skills, read_file intercept) — all
        plugins are already subscribed by then, so no lifecycle hook needed.
        """
        if not ctx.app or not ctx.app.plugin_system:
            return {}
        results = ctx.app.plugin_system.call_hooks("on_internal_skills")
        return _merge_internal_results(results)

    def handle_internal_read(path: str):
        """on_read_file intercept: serve /internal/<skill>/<file> virtual files.

        Returns None for non-internal paths or unknown skills/files — read_file
        falls through to normal sandbox/file handling then.
        """
        if not path.startswith(INTERNAL_PREFIX):
            return None

        rest = path[len(INTERNAL_PREFIX):]
        parts = rest.split("/", 1)
        skill_name = parts[0]
        file_name = parts[1] if len(parts) > 1 and parts[1] else "SKILL.md"
        if not skill_name:
            return None

        skill = internal_registry().get(skill_name)
        if not skill:
            return None

        files = skill.get("files") or {}
        if file_name in files:
            return files[file_name]
        return None

    def handle_skills_command(args_str: str) -> str:
        """Handle /skills command"""
        args = args_str.strip().split(maxsplit=1) if args_str.strip() else []

        if not args:
            internal = internal_registry()
            if not manager.skills and manager.extra_count == 0 and not internal:
                return "No skills directories found (.aicoder/skills* or ~/.config/aicoder-v3/skills*)"
            dirs_display = ", ".join(manager._loaded_dirs)
            output = f"Available Skills (loading from {dirs_display}):\n\n"
            for skill_name, skill_info in sorted(manager.skills.items()):
                source = skill_info.get("source", "unknown")
                output += f"  \u2022 {skill_name} [{source}]\n"
                output += f"    {skill_info['description']}\n\n"
            if internal:
                output += "Internal Skills (virtual — served via read_file):\n\n"
                for name, info in sorted(internal.items()):
                    output += f"  \u2022 {name} ({INTERNAL_PREFIX}{name}/SKILL.md)\n"
                    output += f"    {info.get('description', '')}\n\n"
            if manager.extra_count > 0:
                output += f"[+] {manager.extra_count} extra skill(s) — use /skills extra to list\n"
            output += f"Total: {len(manager.skills)} skill(s) loaded, {len(internal)} internal skill(s)"
            return output

        if args[0] == "extra":
            return manager.list_extra_skills()

        if args[0] == "help":
            return """Skills Commands:

/skills          - Show loaded skills
/skills extra    - List extra (non-auto-loaded) skills
/skills help     - Show this help

Directories:
  ~/.config/aicoder-v3/skills/      READ-ONLY (system-level)
  .aicoder/skills/                  Writable — create/modify skills here
  ~/.config/aicoder-v3/skills-extra/  READ-ONLY
  .aicoder/skills-extra/            Writable

To modify a global skill: copy it from ~/.config/... to .aicoder/skills/ first,
then edit the local copy. The global dir is READ-ONLY to the AI.
Local (.aicoder/) overrides global on name collision.
Any dir: skill_name/SKILL.md with YAML frontmatter."""

        return f"Unknown command: {args[0]}. Use /skills help for usage."

    def on_system_prompt_append():
        return manager.generate_skills_text(internal_registry())

    def on_file_sandbox_whitelist():
        """Whitelist global skills dirs for read-only sandbox access.

        Lets read_file/grep/list_directory reach them from any cwd; write
        tools never consult the whitelist, keeping them READ-ONLY.
        """
        cfg_dir = os.path.expanduser("~/.config/aicoder-v3")
        return [
            os.path.join(cfg_dir, "skills"),
            os.path.join(cfg_dir, "skills-extra"),
        ]

    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)
    ctx.register_hook("on_read_file", handle_internal_read)
    ctx.register_hook("on_file_sandbox_whitelist", on_file_sandbox_whitelist)
    ctx.register_command("skills", handle_skills_command, description="List available skills")

    if Config.debug():
        if count > 0:
            dirs_display = ", ".join(manager._loaded_dirs)
            LogUtils.print(f"[+] Skills plugin loaded ({count} skills found)")
            LogUtils.print(f"  - Loading from: {dirs_display}")
        else:
            LogUtils.print("[+] Skills plugin loaded (0 skills found)")

    def cleanup():
        manager.skills.clear()

    return {"cleanup": cleanup}
