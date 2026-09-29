"""
Git Aware Plugin - Adds git context to AI system prompt

Checks if current directory is a git repo using .git/HEAD stat (no subprocess
at startup). Git subprocess only spawns on first context bar render or /git
command. Non-git repos cost ~1 stat syscall at startup, nothing more.

Commands:
- /git commit-ai - Gather all git info and ask AI to commit in one shot
"""

import os

from aicoder.core.config import Config
from aicoder.tools.internal.run_shell_command import safe_subprocess_run

_subprocess = None

def _get_subprocess():
    global _subprocess
    if _subprocess is None:
        import subprocess
        _subprocess = subprocess
    return _subprocess

# None = not loaded yet, str = branch name, "" = failed to load
_cached_git_branch = None

# Repo-local .git/config is attacker-writable (proven escape vector), so treat
# it as untrusted. Exec-capable keys get forced via -c (CLI config wins over
# repo config): fsmonitor runs a command on status; pager runs if a tty ever
# appears; no builtin hook runs on status/log/diff/branch but gc/locks are
# side effects worth killing. Aliases can't shadow builtins, so "status",
# "log", "diff", "branch" are safe.
_REPO_CONFIG_OVERRIDES = [
    "-c", "core.fsmonitor=false",
    "-c", "core.pager=cat",
    "-c", "gc.auto=0",
]
_REPO_CONFIG_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",  # ignore /etc/gitconfig (same-user untrusted)
    "GIT_TERMINAL_PROMPT": "0",
}


def _spawn_git(args, timeout=10):
    """Run git with all repo-controlled exec paths neutralized"""
    base = ["git", "--no-pager", "--no-optional-locks"] + _REPO_CONFIG_OVERRIDES
    if args and args[0] == "diff":
        # External diff drivers / textconv = arbitrary code exec from .gitattributes
        # (flags go after subcommand, git rejects them at top level)
        base += ["diff", "--no-ext-diff", "--no-textconv"]
        args = args[1:]
    try:
        # safe_subprocess_run routes through the /sec bwrap seal (fail-open:
        # no hook / bwrap absent -> runs argv unwrapped). Env hardening vars
        # are stripped by --clearenv inside the seal; the -c overrides above
        # (argv) carry the real defense either way.
        return safe_subprocess_run(
            base + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **_REPO_CONFIG_ENV},
        )
    except (_get_subprocess().TimeoutExpired, FileNotFoundError, _get_subprocess().SubprocessError):
        return None


def _is_git_repo():
    """Fast check using .git/HEAD — no subprocess, works for worktrees too"""
    return os.path.isfile('.git/HEAD')


def _get_git_branch():
    """Get current git branch, returns None if not a git repo"""
    try:
        result = _spawn_git(["branch", "--show-current"], timeout=5)
        if result is not None and result.returncode == 0:
            return result.stdout.strip()
    except (_get_subprocess().SubprocessError):
        pass
    return None


def create_plugin(ctx):
    """Git awareness plugin"""
    global _cached_git_branch

    # Startup: NO git subprocess. Just stat .git/HEAD (~1 syscall).
    is_git = _is_git_repo()

    if Config.debug():
        if is_git:
            print("[*] Git aware: Repository detected")
        else:
            print("[*] Git aware: Not a git repository")

    def _ensure_branch():
        """Lazy-load branch on first access (context bar or /git)"""
        global _cached_git_branch
        if _cached_git_branch is None and is_git:
            branch = _get_git_branch()
            _cached_git_branch = branch if branch else ""
        return _cached_git_branch if _cached_git_branch else None

    def _is_repo_dirty():
        """Check if repo has uncommitted changes"""
        if not is_git:
            return False
        result = _spawn_git(["status", "--porcelain"], timeout=5)
        return result is not None and result.returncode == 0 and result.stdout.strip()

    def _run_git(args):
        """Run git command with exec paths neutralized, return output"""
        result = _spawn_git(args)
        return result.stdout.strip() if result is not None and result.returncode == 0 else ""

    def _gather_commit_info():
        """Gather all git info needed for AI commit"""
        sections = []
        branch = _ensure_branch()
        sections.append(f"Branch: {branch}" if branch else "Branch: (unknown)")

        # 2. Status
        status = _run_git(["status", "--short"])
        if not status:
            return None  # Nothing to commit
        sections.append(f"\nStatus:\n{status}")

        # 3. Diff (staged + unstaged)
        diff_staged = _run_git(["diff", "--cached"])
        diff_unstaged = _run_git(["diff"])

        if diff_staged:
            sections.append(f"\nStaged diff:\n{diff_staged}")
        if diff_unstaged:
            sections.append(f"\nUnstaged diff:\n{diff_unstaged}")

        # 4. Recent commits for context
        log = _run_git(["log", "--oneline", "-5"])
        if log:
            sections.append(f"\nRecent commits:\n{log}")

        return "\n".join(sections)

    def handle_git_command(args_str: str) -> str:
        """Handle /git command"""
        args = args_str.strip().split() if args_str.strip() else []

        if not args or args[0] in ("-h", "--help", "help"):
            return """Git Plugin

Usage:
    /git ca (or commit-ai)  - Gather git info and ask AI to commit (max 15k chars)
    /git status             - Show git status
    /git diff               - Show git diff
    /git log [n]            - Show last n commits (default: 5)
    /git branch             - Show current branch

The commit-ai command saves API calls by gathering all git context
and sending it to the AI in a single prompt. Refuses if context > 15k chars."""

        subcommand = args[0]
        if subcommand in ("ca", "cai"):
            subcommand = "commit-ai"

        if subcommand == "commit-ai":
            # Refuse if context too big - could blow past context limit
            MAX_COMMIT_CONTEXT = 15000  # chars
            info = _gather_commit_info()
            if info is None:
                return "Nothing to commit - working tree is clean."

            if len(info) > MAX_COMMIT_CONTEXT:
                c = Config.colors
                return (
                    f"{c['red']}[X] Git context too large ({len(info):,} chars){c['reset']}\n"
                    f"{c['yellow']}[i] Try staging fewer files with: git add <files>{c['reset']}\n"
                    f"{c['dim']}Max size: {MAX_COMMIT_CONTEXT:,} chars, got: {len(info):,} chars{c['reset']}"
                )

            prompt = f"""Please commit the following changes. Here is the git context:

{info}

Create a meaningful commit message and run the appropriate git add/commit commands."""

            ctx.app.set_next_prompt(prompt)
            return f"{Config.colors['cyan']}[*] Git context gathered - AI processing commit...{Config.colors['reset']}"

        elif subcommand == "status":
            return _run_git(["status"])

        elif subcommand == "diff":
            raw = _run_git(["diff"])
            if not raw:
                return "No unstaged changes."
            c = Config.colors
            lines = []
            for line in raw.split("\n"):
                if line.startswith("+") and not line.startswith("+++"):
                    lines.append(f"{c['green']}{line}{c['reset']}")
                elif line.startswith("-") and not line.startswith("---"):
                    lines.append(f"{c['red']}{line}{c['reset']}")
                else:
                    lines.append(line)
            return "\n".join(lines)

        elif subcommand == "log":
            n = args[1] if len(args) > 1 else "5"
            return _run_git(["log", f"--oneline", f"-{n}"]) or "No commits yet."

        elif subcommand == "branch":
            raw = _run_git(["branch"])
            if not raw:
                return "Not a git repository."
            c = Config.colors
            lines = []
            for line in raw.split("\n"):
                if line.startswith("* "):
                    lines.append(f"{c['green']}{c['bold']}{line}{c['reset']}")
                else:
                    lines.append(line)
            return "\n".join(lines)

        else:
            return f"Unknown subcommand: {subcommand}\nTry /git --help"

    # Register the /git command
    ctx.register_command("/git", handle_git_command, description="Git operations")

    def on_system_prompt_append():
        """Contribute git context to system prompt during prompt build

        Uses on_system_prompt_append (not before_user_prompt/before_ai_processing)
        to avoid directly mutating msgs[0]. This hook fires during
        build_complete_system_prompt() (on compaction, reload, session init),
        and the returned string is baked into the prompt at build time —
        no desync with _skip_hooks_once, no spurious msg[0]: CHANGED.
        """
        if not is_git:
            return None

        return "\n\nGit repository detected."

    def on_context_bar():
        """Hook: Add git status to context bar"""
        if not is_git:
            return None

        dirty = _is_repo_dirty()
        if dirty:
            return f"{Config.colors['yellow']}{Config.colors['bold']}Git"
        return f"{Config.colors['dim']}Git"

    # Register hooks
    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)
    ctx.register_hook("on_context_bar", on_context_bar)

    if Config.debug():
        print("  - on_system_prompt_append hook (git awareness)")
        print("  - on_context_bar hook (git status)")
        print("  - /git command (commit-ai, status, diff, log, branch)")
