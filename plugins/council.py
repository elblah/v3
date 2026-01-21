"""
Council Plugin - Expert opinions and auto-council
"""

import os
from typing import List, Dict, Any, Optional, Tuple

from aicoder.utils.log import error, warn, info, dim, cyan, success, print as log_print
from aicoder.core.config import Config


# Generic role instructions for normal-mode members
NORMAL_MEMBER_INSTRUCTIONS = """

⚠️ CRITICAL ROLE DEFINITION - READ THIS FIRST ⚠️

YOU ARE A COUNCIL MEMBER. YOU ARE NOT THE IMPLEMENTING AI.

What you DO:
- Answer the user's question based on your expertise
- Analyze the context provided (conversation history, code, test results, etc.)
- Provide your expert perspective and recommendations
- Ask clarifying questions if needed

What you DO NOT DO:
- You NEVER execute tools (read_file, write_file, run_shell_command, etc.)
- You NEVER modify files yourself
- You NEVER run commands yourself
- You NEVER take any actions
- You NEVER implement code or features yourself
- You are an OBSERVER and ADVISOR only

If you need to see code: Ask the implementing AI in text to "Show me the code for X"
If you need to see test results: Ask in text "Show me the test output"
You communicate ONLY through text. The implementing AI will do the work.

---

**HOW TO ANSWER - USE THIS TEMPLATE**:

You will receive:
1. A user question (the original /council command)
2. Full conversation context showing what was done (files written, tests run, etc.)

You CANNOT invoke tools. If you need something, REQUEST it in text.

**STRUCTURE YOUR RESPONSE USING THESE SECTIONS**:

**Analysis**
[Briefly state what you're analyzing from your expertise perspective]

**Findings**
[Bullet points of what you discovered - max 5 items]
- Finding 1
- Finding 2
- ...

**Concerns** (if any)
[Bullet points of issues or problems - max 3 items, omit if none]
- Concern 1
- Concern 2
- ...

**Recommendations**
[Bullet points of expert suggestions - max 3 items]
- Recommendation 1
- Recommendation 2
- ...

**Verdict**
[Your expert opinion in 1-2 sentences: e.g., "On the right track - proceed", "Needs redesign", "Ready for next steps"]

**500 WORD LIMIT**: Maximum 500 words total. Be concise and focused on essential insights only.

If everything looks correct, state "No concerns from my perspective" in the Concerns section.
"""


# Generic voting instructions appended to auto-mode members
AUTO_MEMBER_INSTRUCTIONS = """

⚠️ CRITICAL ROLE DEFINITION - READ THIS FIRST ⚠️

YOU ARE A COUNCIL MEMBER. YOU ARE NOT THE IMPLEMENTING AI.

What you DO:
- Analyze code that was implemented
- Provide feedback and recommendations
- Vote whether implementation is complete

What you DO NOT DO:
- You NEVER execute tools (read_file, write_file, run_shell_command, etc.)
- You NEVER modify files yourself
- You NEVER run commands yourself
- You NEVER take any actions
- You are an OBSERVER and ADVISOR only

If you need to see code: Ask the implementing AI in text to "Show me the code for X"
If you need to see test results: Ask in text "Show me the test output"
You communicate ONLY through text. The implementing AI will do the work.

---

**HOW TO REVIEW**:

Look at the implementation evidence provided in the conversation context. This includes:
- Files that were written (shown in tool output)
- Test results
- Any error messages
- User feedback

You CANNOT invoke tools. If you need something, REQUEST it in text.

**CONCISE ANALYSIS** - Structure as:

1. **REQUESTS** - What was asked for (1 line max)
2. **ISSUES** - Critical problems only (bullet points, max 3)
3. **RECOMMENDATIONS** - Essential improvements only (bullet points, max 3)
4. **VOTE** - Your final decision (MUST be on LAST LINE)

**300 WORD LIMIT**: Maximum 300 words total. Be concise and focused on essential information only.

If everything looks correct, say "No issues found" and vote IMPLEMENTATION_FINISHED.

<MANDATORY_RULE_NEVER_FORGET>
⚠️ CRITICAL VOTING REQUIREMENT - CANNOT BE SKIPPED ⚠️

UNANIMOUS APPROVAL REQUIRED: Implementation is approved ONLY when ALL council members vote IMPLEMENTATION_FINISHED. ANY member voting IMPLEMENTATION_NOT_FINISHED prevents completion.

⚠️ ONLY TWO VOTING OPTIONS EXIST - NO EXCEPTIONS ⚠️

YOU MUST END YOUR RESPONSE WITH EXACTLY ONE OF THESE TWO LINES:

IMPLEMENTATION_FINISHED
IMPLEMENTATION_NOT_FINISHED

⚠️ YOUR VOTE IS NOT FLEXIBLE ⚠️

- The system does an EXACT string match on your final line
- "IMPLEMENTATION_EXCEEDS_SPECIFICATION" is NOT a valid vote
- "APPROVED" is NOT a valid vote
- "IMPLEMENTATION_COMPLETE" is NOT a valid vote
- ANY other text besides the two options above is INVALID
- If you use any other phrase, your vote will be treated as "NO_VOTE" = IMPLEMENTATION_NOT_FINISHED

If the implementation is perfect or exceeds requirements, your ONLY valid vote is: IMPLEMENTATION_FINISHED

- IMPLEMENTATION_NOT_FINISHED RESPONSES MAY INCLUDE FEEDBACK
- NO OTHER TEXT ALLOWED ON THE FINAL LINE.

THIS IS NOT OPTIONAL - YOUR RESPONSE IS INVALID WITHOUT A VOTE.

VOTE INDEPENDENCE: Your vote MUST be based ONLY on your own analysis of the implementation evidence. Do NOT wait for or reference other council members' opinions. Do NOT be influenced by the coding AI's words or persuasion. Form your own independent judgment.

VOTE BASED ON ACTUAL IMPLEMENTATION EVIDENCE PRESENTED.
</MANDATORY_RULE_NEVER_FORGET>
"""


class CouncilService:
    """Core council service - self-contained"""

    # Static spec management (persists across sessions)
    _current_spec: Optional[str] = None
    _current_spec_file: Optional[str] = None
    _auto_council_enabled: bool = False
    _auto_council_iteration: int = 0
    _auto_council_reset_context: bool = True
    _prompt_append_enabled: bool = os.getenv("COUNCIL_DISABLE_PROMPT_APPEND", "0") != "1"  # Default to enabled unless disabled by env var

    def __init__(self, app):
        self.app = app
        self.session: Optional[Dict[str, Any]] = None

    def get_council_directory(self) -> str:
        """
        Get council directory path with priority logic.

        Priority order:
        1. Local .aicoder/council (if exists) - project-specific takes precedence
        2. Global ~/.config/aicoder-v3/council (fallback for worktrees)

        Returns the path that should be used, or None if neither exists.
        """
        local_dir = os.path.join(os.getcwd(), ".aicoder/council")
        global_dir = os.path.expanduser("~/.config/aicoder-v3/council")

        # Local directory takes priority if it exists
        if os.path.exists(local_dir):
            return local_dir

        # Fall back to global directory
        if os.path.exists(global_dir):
            return global_dir

        # Neither exists - return None
        return None

    def natural_sort(self, files: List[str]) -> List[str]:
        """Natural sort: numbered first (1_, 2_, ...) then alphabetical"""
        def sort_key(f):
            name = os.path.splitext(f)[0]
            match = name.split("_")[0]
            if match.isdigit():
                return (0, int(match))
            return (1, name)
        return sorted(files, key=sort_key)

    def load_members(
        self,
        filters: Optional[List[str]] = None,
        auto_mode: bool = False,
        include_disabled: bool = False
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Load council members from filesystem with priority logic.

        Priority:
        1. Local .aicoder/council (if exists)
        2. Global ~/.config/aicoder-v3/council (fallback)
        """
        council_dir = self.get_council_directory()

        if not council_dir:
            error("Council directory not found")
            log_print("Create either:")
            dim("  - .aicoder/council/ (project-specific)")
            dim("  - ~/.config/aicoder-v3/council/ (global)")
            return [], None

        files = os.listdir(council_dir)
        sorted_files = self.natural_sort(files)
        members = []
        moderator = None

        for filename in sorted_files:
            if not filename.endswith(".txt"):
                continue

            name = filename.replace(".txt", "")

            if not include_disabled and name.startswith("_"):
                continue

            if auto_mode and not name.endswith("_auto") and "moderator" not in name.lower():
                continue
            elif not auto_mode and name.endswith("_auto") and not include_disabled:
                continue

            if filters:
                matches = False
                for f in filters:
                    try:
                        target_number = int(f)
                        display_files = [f for f in sorted_files if f.endswith(".txt") and "moderator" not in f.lower()]
                        member_index = display_files.index(filename) if filename in display_files else -1
                        if member_index == target_number - 1:
                            matches = True
                            break
                    except ValueError:
                        if f.lower() in name.lower():
                            matches = True
                            break
                if not matches:
                    continue

            try:
                filepath = os.path.join(council_dir, filename)
                with open(filepath, "r") as f:
                    prompt = f.read().strip()

                if not prompt:
                    continue

                if "moderator" in name.lower():
                    if auto_mode and name.endswith("_auto"):
                        moderator = {"name": name, "prompt": prompt}
                        continue
                    if not auto_mode and name.endswith("_auto") and moderator:
                        continue
                    if not moderator:
                        moderator = {"name": name, "prompt": prompt}
                    continue

                members.append({"name": name, "prompt": prompt, "is_auto_member": name.endswith("_auto")})

            except Exception as e:
                if Config.debug():
                    warn(f"Failed to load member {filename}: {e}")

        return members, moderator

    def parse_vote(self, opinion: str) -> Optional[str]:
        """Parse IMPLEMENTATION_FINISHED or IMPLEMENTATION_NOT_FINISHED"""
        lines = opinion.strip().split("\n")
        last_line = lines[-1].strip() if lines else ""

        if "IMPLEMENTATION_FINISHED" in last_line:
            return "FINISHED"
        elif "IMPLEMENTATION_NOT_FINISHED" in last_line:
            return "NOT_FINISHED"

        return None

    def get_member_opinion(
        self,
        member: Dict[str, Any],
        user_request: str,
        include_spec: bool = False
    ) -> str:
        """Get opinion from council member with retry logic"""
        from aicoder.core.ai_processor import AIProcessor

        # Build system prompt
        system_prompt = f"You are {member['name']}.\n\n{member['prompt']}"

        # Add generic instructions based on member type (if append enabled)
        if CouncilService._prompt_append_enabled:
            if member.get("is_auto_member", False):
                system_prompt += AUTO_MEMBER_INSTRUCTIONS
            else:
                system_prompt += NORMAL_MEMBER_INSTRUCTIONS

        # Build full context from message history
        # Filter out system messages, include tool calls
        messages = self.app.message_history.get_messages() if self.app.message_history else []

        context_lines = []
        for msg in messages:
            if msg.get("role") == "system":
                continue

            line = f"{msg['role']}:"

            # Add content
            content = msg.get("content", "")
            if content:
                line += f" {content}"

            # Add tool calls (format: [write_file(...)] [read_file(...)])
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                tool_call_strs = []
                for tc in tool_calls:
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    args = func.get("arguments", "")
                    tool_call_strs.append(f"[{name}({args})]")
                line += " " + " ".join(tool_call_strs)

            context_lines.append(line)

        # Combine context
        context = "\n".join(context_lines)

        # Prepare messages for API call
        messages_for_api = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User request:\n{user_request}\n\nContext:\n{context}"}
        ]

        # Add spec if requested
        if include_spec and CouncilService.has_spec():
            spec = CouncilService.get_current_spec()
            messages_for_api.append({"role": "user", "content": f"\n\nSpecification to review:\n{spec}"})

        # Call AI
        result = AIProcessor.process_single(messages_for_api, max_tokens=2000)
        return result.content if result else "No response from council member"

    def get_direct_expert_opinions(
        self,
        members: List[Dict[str, Any]],
        user_request: str
    ) -> str:
        """Get direct expert opinions (no moderator)"""
        opinions = []

        for member in members:
            cyan(f"\n{member['name']}:")

            opinion = self.get_member_opinion(member, user_request, include_spec=False)
            opinions.append(f"{member['name']}:\n{opinion}")

        return "\n\n".join(opinions)

    def start_session(self, messages: List[Dict[str, Any]], auto_mode: bool = False) -> None:
        """Start a new council session"""
        self.session = {
            "original_messages": messages.copy(),
            "opinions": {},
            "consensus_achieved": False,
            "final_plan": None,
            "is_auto_mode": auto_mode
        }
        cyan("Council session started")

    def get_session_status(self) -> Optional[Dict[str, Any]]:
        """Get current session status"""
        return self.session

    def clear_session(self) -> None:
        """Clear current session"""
        self.session = None
        log_print("Council session cleared")

    # Spec management (static methods)
    @staticmethod
    def load_spec(spec_content: str, spec_file: str) -> None:
        """Load specification"""
        CouncilService._current_spec = spec_content
        CouncilService._current_spec_file = spec_file

        spec_dir = ".aicoder"
        os.makedirs(spec_dir, exist_ok=True)
        spec_path = os.path.join(spec_dir, "current-spec.md")

        with open(spec_path, "w") as f:
            f.write(spec_content)

    @staticmethod
    def has_spec() -> bool:
        """Check if spec is loaded"""
        return CouncilService._current_spec is not None

    @staticmethod
    def get_current_spec() -> Optional[str]:
        """Get current spec content"""
        return CouncilService._current_spec

    @staticmethod
    def get_current_spec_file() -> Optional[str]:
        """Get current spec file path"""
        return CouncilService._current_spec_file

    @staticmethod
    def clear_spec() -> None:
        """Clear specification"""
        CouncilService._current_spec = None
        CouncilService._current_spec_file = None

    # Auto-council integration
    def handle_auto_council_trigger(self, has_tool_calls: bool) -> Optional[str]:
        """Hook handler called after AI processing. Runs council review and queues next iteration if needed."""
        # Only trigger when AI is done (no tool calls) - handing over to user
        if has_tool_calls:
            return None

        if not CouncilService._auto_council_enabled:
            return None

        if not CouncilService.has_spec():
            return None

        max_iterations = int(os.getenv("COUNCIL_MAX_ITERATIONS", "10"))
        if CouncilService._auto_council_iteration >= max_iterations:
            warn("Auto-council max iterations reached")
            self.disable_auto_council()
            return None

        CouncilService._auto_council_iteration += 1
        cyan(f"\n[Auto-Council] Iteration {CouncilService._auto_council_iteration}")

        # Get context for council review
        messages = self.app.message_history.get_messages() if self.app.message_history else []

        # Run auto-council review
        feedback = self.run_auto_council_review(messages)

        # If implementation complete, disable auto-council
        if "All council members approve" in feedback:
            success("Auto-council complete - implementation approved!")
            self.disable_auto_council()
            return None

        # Queue next iteration
        CouncilService._auto_council_reset_context = False
        self.app.message_history.add_user_message(f"Council feedback:\n{feedback}")

        return feedback

    @staticmethod
    def enable_auto_council(reset_context: bool = True) -> None:
        """Enable auto-council mode"""
        CouncilService._auto_council_enabled = True
        CouncilService._auto_council_reset_context = reset_context
        CouncilService._auto_council_iteration = 0
        success("Auto-council enabled")

    @staticmethod
    def disable_auto_council() -> None:
        """Disable auto-council mode"""
        CouncilService._auto_council_enabled = False
        CouncilService.clear_spec()
        warn("Auto-council disabled")

    def run_auto_council_review(self, messages: List[Dict[str, Any]]) -> str:
        """Run council review in auto-mode"""
        members, moderator = self.load_members(auto_mode=True)

        if not members:
            return "No council members found for auto-review"

        cyan(f"\n[Auto-Council] Reviewing with {len(members)} members")

        opinions = {}
        votes = {}

        for member in members:
            cyan(f"\n{member['name']}:")
            opinion = self.get_member_opinion(member, "Review this implementation", include_spec=True)
            opinions[member['name']] = opinion
            log_print(opinion)

            # Parse vote
            vote = self.parse_vote(opinion)
            votes[member['name']] = vote

        # Build vote summary
        finished_count = sum(1 for v in votes.values() if v == "FINISHED")
        not_finished_count = sum(1 for v in votes.values() if v == "NOT_FINISHED")

        # Check for consensus
        if not moderator:
            # No moderator - need unanimous approval
            if not_finished_count > 0:
                return f"Implementation NOT approved ({not_finished_count} member(s) found issues). Review feedback above and try again."
            return f"All council members approve! ({finished_count}/{len(members)})"

        # With moderator: moderator synthesizes
        moderator_opinion = self.get_member_opinion(moderator, f"Opinions: {opinions}", include_spec=False)
        consensus = self.parse_vote(moderator_opinion)

        # Return feedback
        feedback = f"Auto-council iteration {CouncilService._auto_council_iteration}\n"
        feedback += f"Votes: {finished_count} FINISHED, {not_finished_count} NOT_FINISHED\n"
        if moderator:
            feedback += f"\nModerator: {moderator['name']}\n{moderator_opinion}"

        if consensus == "FINISHED" and not_finished_count == 0:
            feedback = "All council members approve! Implementation complete."
        elif consensus == "NOT_FINISHED":
            feedback = f"Implementation needs revision. {not_finished_count} member(s) found issues."
        else:
            feedback += "\nAwaiting revisions..."

        return feedback

    @staticmethod
    def is_prompt_append_enabled() -> bool:
        """Check if prompt append is enabled"""
        return CouncilService._prompt_append_enabled

    @staticmethod
    def enable_prompt_append() -> None:
        """Enable prompt append"""
        CouncilService._prompt_append_enabled = True
        success("Prompt append enabled")

    @staticmethod
    def disable_prompt_append() -> None:
        """Disable prompt append"""
        CouncilService._prompt_append_enabled = False
        warn("Prompt append disabled")


class CouncilPlugin:
    """Council plugin for AI Coder"""

    def __init__(self, app):
        self.app = app
        self.service = CouncilService(app)

    def handle_council(self, args: str) -> str:
        """Handle /council command"""
        if not args:
            self._show_help()
            return ""

        parts = args.split()
        subcommand = parts[0].lower()

        handlers = {
            "list": self._handle_list,
            "members": self._handle_list,
            "run": self._handle_run,
            "start": self._handle_run,
            "review": self._handle_review,
            "cancel": self._handle_cancel,
            "status": self._handle_status,
            "accept": self._handle_accept,
            "edit": self._handle_edit,
            "enable": lambda a: self._toggle_member(a, True),
            "disable": lambda a: self._toggle_member(a, False),
            "prompt-append": self._handle_prompt_append,
            "auto": self._handle_auto,
        }

        handler = handlers.get(subcommand)
        if handler:
            return handler(" ".join(parts[1:]))

        warn(f"Unknown council subcommand: {subcommand}")
        return ""

    def _handle_list(self, args: str) -> str:
        """List council members"""
        council_dir = self.service.get_council_directory()

        if not council_dir:
            error("Council directory not found")
            dim("Create either:")
            dim("  - .aicoder/council/ (project-specific)")
            dim("  - ~/.config/aicoder-v3/council/ (global)")
            return ""

        files = os.listdir(council_dir)
        sorted_files = self.service.natural_sort(files)
        member_files = [f for f in sorted_files if f.endswith(".txt") and "moderator" not in f.lower()]

        cyan("Council Members:")
        log_print("")
        warn(f"Directory: {council_dir}")
        log_print("")

        if member_files:
            info("Members:")
            for idx, member_file in enumerate(member_files, 1):
                name = member_file.replace(".txt", "")
                is_disabled = name.startswith("_")
                status = " (disabled)" if is_disabled else ""
                if is_disabled:
                    dim(f"  {idx}) {name}{status}")
                else:
                    log_print(f"  {idx}) {name}{status}")

        if any("moderator" in f.lower() for f in sorted_files):
            log_print("")
            success("Moderator (always included):")
            dim("  - moderator")

        return ""

    def _handle_run(self, args: str) -> str:
        """Run council session"""
        parts = args.split()
        auto_mode = "--auto" in parts or "-a" in parts
        filters = [p for p in parts if not p.startswith("-")]

        if auto_mode and not CouncilService.has_spec():
            error("No specification loaded. Use /council auto <spec-file> or /council auto '<spec-content>'")
            return ""

        if auto_mode:
            if not filters:
                error("Usage: /council run --auto <spec-file> or /council run --auto '<spec-content>'")
                return ""

            # Check if it's a file or inline content
            spec_content = filters[0]
            if os.path.exists(spec_content):
                with open(spec_content, "r") as f:
                    spec_content = f.read()
                CouncilService.load_spec(spec_content, spec_content)
                CouncilService.enable_auto_council()
                success("Specification loaded")
                cyan("\nStarting implementation...")
                self.app.message_history.add_user_message(f"Specification to implement:\n\n{spec_content}")
            else:
                # Inline spec
                CouncilService.load_spec(spec_content, "inline-spec.md")
                CouncilService.enable_auto_council()
                success("Specification loaded from text")
                cyan("\nStarting implementation...")
                self.app.message_history.add_user_message(f"Specification to implement:\n\n{spec_content}")
        else:
            # Normal council session
            members, moderator = self.service.load_members(filters if filters else None)

            if not members and not moderator:
                warn("No council members found")
                return ""

            # Get direct opinions or moderator synthesis
            if moderator:
                result = self.service.get_consensus(moderator, {})
            else:
                result = self.service.get_direct_expert_opinions(members, args)

            self.service.clear_session()

            if result:
                log_print("")
                cyan(f"\nCouncil review ({len(members)} members)")
                log_print("")
                success(result)

        return ""

    def _handle_review(self, args: str) -> str:
        """Show current council review status"""
        session = self.service.get_session_status()

        if not session or not session.get("final_plan"):
            warn("No active council session")
            return ""

        cyan("Current Council Review:")
        success(session["final_plan"])
        return ""

    def _handle_accept(self, args: str) -> str:
        """Accept council plan"""
        session = self.service.get_session_status()

        if not session or not session.get("final_plan"):
            warn("No final plan to accept")
            return ""

        final_plan = session["final_plan"]
        self.app.message_history.add_user_message(f"Council feedback: {final_plan}")

        success("Council plan injected into conversation")
        cyan("AI will now consider this feedback")

        self.service.clear_session()
        return ""

    def _handle_cancel(self, args: str) -> str:
        """Cancel council session"""
        CouncilService._auto_council_enabled = False
        CouncilService.clear_spec()

        warn("Council cancelled. All state cleared.")
        return ""

    def _handle_edit(self, args: str) -> str:
        """Edit council member file"""
        if not args:
            warn("Usage: /council edit <number|name>")
            return ""

        council_dir = self.service.get_council_directory()

        if not council_dir:
            error("Council directory not found")
            return ""

        files = os.listdir(council_dir)
        sorted_files = self.service.natural_sort(files)
        member_files = [f for f in sorted_files if f.endswith(".txt")]

        target_file = None
        try:
            idx = int(args) - 1
            if 0 <= idx < len(member_files):
                target_file = member_files[idx]
        except ValueError:
            # Try name match
            for f in member_files:
                if args.lower() in f.lower():
                    target_file = f
                    break

        if not target_file:
            error(f"Cannot find council member: {args}")
            return ""

        # Find editor
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"

        filepath = os.path.join(council_dir, target_file)
        os.system(f"{editor} {filepath}")
        success(f"Edited: {target_file}")

        return ""

    def _toggle_member(self, args: str, enabled: bool) -> str:
        """Enable or disable council member"""
        if not args:
            warn(f"Usage: /council {'enable' if enabled else 'disable'} <number|name>")
            return ""

        council_dir = self.service.get_council_directory()

        if not council_dir:
            error("Council directory not found")
            return ""

        files = os.listdir(council_dir)
        sorted_files = self.service.natural_sort(files)
        member_files = [f for f in sorted_files if f.endswith(".txt")]

        target_file = None
        try:
            idx = int(args) - 1
            if 0 <= idx < len(member_files):
                target_file = member_files[idx]
        except ValueError:
            # Try name match
            for f in member_files:
                if args.lower() in f.lower():
                    target_file = f
                    break

        if not target_file:
            error(f"Cannot find council member: {args}")
            return ""

        filepath = os.path.join(council_dir, target_file)

        # Rename file
        if enabled:
            new_name = target_file[2:] if target_file.startswith("_") else target_file
            new_filepath = os.path.join(council_dir, new_name)
            if new_filepath != filepath:
                os.rename(filepath, new_filepath)
                success(f"Enabled: {new_name}")
        else:
            new_name = f"_{target_file}" if not target_file.startswith("_") else target_file
            new_filepath = os.path.join(council_dir, new_name)
            if new_filepath != filepath:
                os.rename(filepath, new_filepath)
                warn(f"Disabled: {new_name}")

        return ""

    def _handle_prompt_append(self, args: str) -> str:
        """Enable or disable prompt append"""
        if not args:
            status = "enabled" if CouncilService.is_prompt_append_enabled() else "disabled"
            cyan(f"Prompt append is currently {status}")
            return ""

        if args.lower() in ("on", "true", "1", "enable"):
            CouncilService.enable_prompt_append()
        elif args.lower() in ("off", "false", "0", "disable"):
            CouncilService.disable_prompt_append()
        else:
            warn("Usage: /council prompt-append on|off (enable|disable)")
            return ""

        return ""

    def _handle_auto(self, args: str) -> str:
        """Load spec and enable auto-council"""
        if not args:
            if CouncilService.has_spec():
                info("Auto-council specification loaded")
            else:
                warn("No specification loaded. Usage: /council auto <spec-file> or /council auto '<spec-content>'")
            return ""

        parts = args.split()
        reset_context = "--reset" in parts or "-r" in parts

        spec_arg = parts[0]

        # Check if it's a file or inline content
        if os.path.exists(spec_arg):
            with open(spec_arg, "r") as f:
                spec_content = f.read()
            CouncilService.load_spec(spec_content, spec_arg)
            CouncilService.enable_auto_council(reset_context)
            success("Specification loaded")
        else:
            # Inline spec
            CouncilService.load_spec(spec_arg, "inline-spec.md")
            CouncilService.enable_auto_council(reset_context)
            success("Specification loaded from text")

        return ""

    def cleanup(self) -> None:
        """Cleanup when plugin is unloaded"""
        CouncilService._auto_council_enabled = False

    def _show_help(self) -> None:
        """Show council help"""
        help_text = """
Council Plugin - Multi-expert advisory system

USAGE:
    /council [subcommand] [options]

SUBCOMMANDS:
    list, members           List available council members
    run [filters]           Run council with optional filters (names or numbers)
    run --auto <spec>       Run auto-council with specification
    review                  Show current council review status
    accept                  Accept council plan and inject into conversation
    cancel                  Cancel council session
    edit <number|name>      Edit council member file
    enable <number|name>    Enable disabled council member
    disable <number|name>   Disable council member
    prompt-append on|off    Enable/disable adding extra instructions to prompts
    auto <spec>             Load spec and enable auto-council (shortcut for run --auto)

EXAMPLES:
    /council list                        List all council members
    /council run 1 2                     Run council with members 1 and 2
    /council run --auto spec.md          Auto-council with specification file
    /council run --auto 'implement X'    Auto-council with inline specification
    /council edit 1                      Edit member 1's instructions
    /council disable 3                   Disable member 3
    /council prompt-append off           Disable extra prompt instructions

AUTO-COUNCIL:
    Auto-council runs after each AI response to review implementation.
    All members must vote IMPLEMENTATION_FISHED for completion.
    Use /council cancel to stop auto-council mode.

COUNCIL DIRECTORIES:
    - .aicoder/council/ (project-specific, highest priority)
    - ~/.config/aicoder-v3/council/ (global fallback)
"""
        log_print(help_text)


def create_plugin(app):
    """Create council plugin"""
    council_service = CouncilService(app)
    council_plugin = CouncilPlugin(app)

    app.register_command("council", council_plugin.handle_council, "Multi-expert advisory system")
    app.register_command("council-cancel", lambda a: council_plugin._handle_cancel(""), "Cancel council session")

    if Config.debug():
        log_print("[+] Council plugin loaded")
        log_print("  - /council command")
        log_print("  - /council-cancel command")
        log_print("  - Auto-council support")

    return {"cleanup": council_service.cleanup}
