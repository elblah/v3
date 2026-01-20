"""
Council Plugin - Expert opinions and auto-council
"""

import os
import time
from typing import List, Dict, Any, Optional, Tuple

from aicoder.utils.log import LogUtils, LogOptions
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
            LogUtils.error("Council directory not found")
            LogUtils.print("Create either:")
            LogUtils.print("  - .aicoder/council/ (project-specific)", LogOptions(color=Config.colors["dim"]))
            LogUtils.print("  - ~/.config/aicoder-v3/council/ (global)", LogOptions(color=Config.colors["dim"]))
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
                    LogUtils.warn(f"Failed to load member {filename}: {e}")

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

        # Join context with newlines
        context_text = "\n".join(context_lines)

        # Add user request if provided
        if user_request:
            context_text += f"\nuser: {user_request}"

        # Add spec if needed
        if include_spec and CouncilService._current_spec:
            context_text += f"\n\nSpecification:\n{CouncilService._current_spec}\n"

        # Build messages for AIProcessor (system + full context as user message)
        messages_for_processor = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_text}
        ]

        processor = AIProcessor(self.app.streaming_client)

        max_retries = Config.effective_max_retries()
        for attempt in range(1, max_retries + 1) if max_retries > 0 else range(1, 999):
            try:
                response = processor.process_messages(
                    messages=messages_for_processor,
                    prompt="",
                    send_tools=False,
                )
                return response.strip()

            except Exception as e:
                if attempt >= max_retries and max_retries > 0:
                    LogUtils.error(f"Council member {member['name']} failed after {max_retries} attempts: {e}")
                    return f"Error: Failed to get opinion from {member['name']}"

                delay = min(2 ** attempt, 64)
                LogUtils.warn(f"Council member {member['name']} - Attempt {attempt}/{max_retries if max_retries > 0 else 'unlimited'} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)

        return f"Error: Failed to get opinion from {member['name']}"


    def get_consensus(
        self,
        moderator: Optional[Dict[str, Any]],
        member_opinions: Dict[str, str]
    ) -> str:
        """Get final consensus moderated by moderator"""
        if not moderator:
            return "\n".join([f"{name}:\n{opinion}" for name, opinion in member_opinions.items()])

        opinions_text = "\n".join([f"{name}:\n{opinion}" for name, opinion in member_opinions.items()])

        prompt = f"""Synthesize these council member opinions into a clear, actionable summary:

{opinions_text}

Provide a prioritized list of improvements and a clear summary."""

        return self.get_member_opinion(moderator, prompt, include_spec=False)


    def get_direct_expert_opinions(
        self,
        members: List[Dict[str, Any]],
        user_request: str
    ) -> str:
        """Get direct expert opinions (no moderator)"""
        opinions = []

        for member in members:
            LogUtils.print(f"\n{member['name']}:", LogOptions(color=Config.colors["cyan"]))

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
        LogUtils.print("Council session started", LogOptions(color=Config.colors["cyan"]))

    def get_session_status(self) -> Optional[Dict[str, Any]]:
        """Get current session status"""
        return self.session

    def clear_session(self) -> None:
        """Clear current session"""
        self.session = None
        LogUtils.print("Council session cleared")

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
            LogUtils.warn("Auto-council max iterations reached")
            self.disable_auto_council()
            return None

        CouncilService._auto_council_iteration += 1
        LogUtils.print(f"\n[Auto-Council] Iteration {CouncilService._auto_council_iteration}", LogOptions(color=Config.colors["cyan"]))

        # Get context for council review
        messages = self.app.message_history.get_messages() if self.app.message_history else []

        # Run auto-council review
        feedback = self.run_auto_council_review(messages)

        # If implementation complete, disable auto-council
        if "All council members approve" in feedback:
            LogUtils.print("Auto-council complete - implementation approved!", LogOptions(color=Config.colors["green"]))
            self.disable_auto_council()
            return None

        # Inject feedback into conversation
        self.app.message_history.add_user_message(feedback)

        # Queue next AI iteration with the feedback
        self.app.set_next_prompt("Continue with the feedback above")

        return None

    def enable_auto_council(self, reset_context: bool = True) -> None:
        """Enable auto-council mode"""
        CouncilService._auto_council_enabled = True
        CouncilService._auto_council_reset_context = reset_context
        CouncilService._auto_council_iteration = 0
        LogUtils.print("Auto-council enabled", LogOptions(color=Config.colors["green"]))

    def disable_auto_council(self) -> None:
        """Disable auto-council mode"""
        CouncilService._auto_council_enabled = False
        CouncilService.clear_spec()
        LogUtils.print("Auto-council disabled", LogOptions(color=Config.colors["yellow"]))

    def run_auto_council_review(self, messages: List[Dict[str, Any]]) -> str:
        """Run auto-council review without moderator API call"""
        self.start_session(messages, auto_mode=True)
        members, _ = self.load_members(None, auto_mode=True)

        if not members:
            return "No council members available for auto-council."

        opinions = {}
        votes = {}

        for member in members:
            LogUtils.print(f"\n{member['name']}:", LogOptions(color=Config.colors["cyan"]))

            opinion = self.get_member_opinion(member, "Review this implementation", include_spec=True)
            opinions[member['name']] = opinion

            vote = self.parse_vote(opinion)
            votes[member['name']] = vote

            LogUtils.print(opinion)

        # Build vote summary
        finished_count = sum(1 for v in votes.values() if v == "FINISHED")
        not_finished_count = sum(1 for v in votes.values() if v == "NOT_FINISHED")
        no_vote_count = sum(1 for v in votes.values() if v is None)

        # Only approve when ALL members explicitly vote FINISHED
        total_members = len(members)
        if finished_count == total_members:
            return "All council members approve. Implementation is complete."

        # Build feedback summary with votes (show NO_VOTE explicitly)
        feedback_parts = []
        if no_vote_count > 0:
            feedback_parts.append(f"{no_vote_count} NO_VOTE (empty/no response)")
        if not_finished_count > 0:
            feedback_parts.append(f"{not_finished_count} NOT_FINISHED")
        if finished_count > 0:
            feedback_parts.append(f"{finished_count} FINISHED")

        feedback = [f"Council feedback ({', '.join(feedback_parts)}):", ""]

        for member, opinion in opinions.items():
            vote = votes.get(member, "NO_VOTE")
            # Show empty opinion as [NO_RESPONSE]
            display_opinion = opinion if opinion.strip() else "[NO_RESPONSE]"
            feedback.append(f"{member} ({vote}):")
            feedback.append(display_opinion)
            feedback.append("")

        return "\n".join(feedback)

    # Prompt append management (static methods)
    @staticmethod
    def enable_prompt_append() -> None:
        """Enable prompt append"""
        CouncilService._prompt_append_enabled = True
        LogUtils.print("Prompt append enabled", LogOptions(color=Config.colors["green"]))

    @staticmethod
    def disable_prompt_append() -> None:
        """Disable prompt append"""
        CouncilService._prompt_append_enabled = False
        LogUtils.print("Prompt append disabled", LogOptions(color=Config.colors["yellow"]))

    @staticmethod
    def is_prompt_append_enabled() -> bool:
        """Check if prompt append is enabled"""
        return CouncilService._prompt_append_enabled

    def cleanup(self) -> None:
        """Cleanup resources"""
        CouncilService.clear_spec()
        CouncilService._auto_council_enabled = False


class CouncilCommand:
    """Council command handler"""

    def __init__(self, council_service: CouncilService, app):
        self.service = council_service
        self.app = app

    def handle(self, args_str: str) -> str:
        """Parse and handle council command"""
        args = args_str.strip().split() if args_str.strip() else []

        if not args:
            return self.show_help()

        subcommand = args[0].lower()

        if subcommand == "current":
            return self.show_current_plan()
        elif subcommand == "accept":
            return self.accept_plan()
        elif subcommand == "clear":
            return self.clear_session()
        elif subcommand == "list":
            return self.list_members()
        elif subcommand == "edit":
            return self.edit_member(args[1:])
        elif subcommand == "enable":
            return self.toggle_member(args[1:], True)
        elif subcommand == "disable":
            return self.toggle_member(args[1:], False)
        elif subcommand == "cancel":
            return self.cancel(args_str)
        elif subcommand == "prompt-append":
            return self.toggle_prompt_append(args[1:])
        elif subcommand == "help":
            return self.show_help()
        else:
            return self.execute_council(args)

    def execute_council(self, args: List[str]) -> str:
        """Execute council query"""
        auto_mode = False
        direct_mode = False
        reset_context = CouncilService._auto_council_reset_context
        filters = []
        message_parts = []

        i = 0
        while i < len(args):
            arg = args[i].lower()

            if arg == "--auto":
                auto_mode = True
                i += 1
            elif arg == "--direct":
                direct_mode = True
                i += 1
            elif arg == "--reset-context":
                reset_context = True
                i += 1
            elif arg == "--no-reset":
                reset_context = False
                i += 1
            elif arg == "--members" and i + 1 < len(args):
                filters = args[i + 1].split(",")
                i += 2
            else:
                # Unknown argument - treat as message
                message_parts.extend(args[i:])
                break

        message = " ".join(message_parts)

        if auto_mode:
            if not message:
                return self.handle_auto_edit()
            elif " " not in message:
                spec_file = message
                if not os.path.exists(spec_file):
                    LogUtils.error(f"File not found: {spec_file}")
                    return ""

                with open(spec_file, "r") as f:
                    spec_content = f.read()

                CouncilService.load_spec(spec_content, spec_file)
                CouncilService.enable_auto_council(reset_context)
                LogUtils.print("Specification loaded", LogOptions(color=Config.colors["green"]))
                LogUtils.print("\nStarting implementation...", LogOptions(color=Config.colors["cyan"]))

                self.app.message_history.add_user_message(f"Specification to implement:\n\n{spec_content}")
                self.app.set_next_prompt("Implement this specification")
                return ""

            CouncilService.load_spec(message, "inline-spec.md")
            CouncilService.enable_auto_council(reset_context)
            LogUtils.print("Specification loaded from text", LogOptions(color=Config.colors["green"]))
            LogUtils.print("\nStarting implementation...", LogOptions(color=Config.colors["cyan"]))

            self.app.message_history.add_user_message(f"Specification to implement:\n\n{message}")
            self.app.set_next_prompt("Implement this specification")
            return ""

        if not message:
            return self.show_help()

        self.start_council(message, direct_mode, filters)
        return ""

    def start_council(
        self,
        message: str,
        direct_mode: bool,
        filters: List[str]
    ) -> None:
        """Start council review (normal mode)"""
        messages = self.app.message_history.get_messages() if self.app.message_history else []
        self.service.start_session(messages, auto_mode=False)

        members, moderator = self.service.load_members(filters, auto_mode=False)

        if not members and not moderator:
            LogUtils.error("No council members found")
            return

        LogUtils.print(f"\nCouncil review ({len(members)} members)", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print("", LogOptions(color=Config.colors["white"]))

        # Get all opinions first (always display them)
        opinions = {}
        for member in members:
            LogUtils.print(f"\n{member['name']}:", LogOptions(color=Config.colors["cyan"]))
            opinion = self.service.get_member_opinion(member, message, include_spec=False)
            opinions[member['name']] = opinion
            LogUtils.print(opinion)

        # Build final plan based on mode and moderator availability
        if direct_mode:
            # Direct mode: no final plan needed, already displayed
            result = ""
        elif moderator:
            # Normal mode with moderator: ask moderator to synthesize
            result = self.service.get_consensus(moderator, opinions)
            LogUtils.print("\n[Moderator] Synthesis (token-efficient)", LogOptions(color=Config.colors["cyan"]))
        else:
            # Normal mode without moderator: opinions are the plan
            result = ""
            LogUtils.print("\n[Direct] Using expert opinions (no moderator available)", LogOptions(color=Config.colors["yellow"]))

        if self.service.session:
            self.service.session["opinions"] = opinions
            self.service.session["final_plan"] = result

        if result:
            LogUtils.print("", LogOptions(color=Config.colors["white"]))
            LogUtils.print(result, LogOptions(color=Config.colors["green"]))

        # Auto-mode: automatically inject feedback

    def handle_auto_edit(self) -> str:
        """Handle auto-mode with editor"""
        editor = os.getenv("EDITOR", "vim")
        spec_file = "/tmp/council-spec.md"

        template = """# Specification

Write your specification here...

## Requirements

- Requirement 1
- Requirement 2

## Success Criteria

- Criterion 1
- Criterion 2
"""

        with open(spec_file, "w") as f:
            f.write(template)

        os.system(f"{editor} {spec_file}")

        with open(spec_file, "r") as f:
            spec_content = f.read()

        CouncilService.load_spec(spec_content, spec_file)
        CouncilService.enable_auto_council()
        LogUtils.print("Specification loaded", LogOptions(color=Config.colors["green"]))

        return ""

    def show_current_plan(self) -> str:
        """Show current council plan"""
        session = self.service.get_session_status()

        if not session or not session.get("final_plan"):
            LogUtils.print("No active council session", LogOptions(color=Config.colors["yellow"]))
            return ""

        LogUtils.print("Current Council Review:", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print(session["final_plan"], LogOptions(color=Config.colors["green"]))
        return ""

    def accept_plan(self) -> str:
        """Accept and inject plan into conversation"""
        session = self.service.get_session_status()

        if not session or not session.get("final_plan"):
            LogUtils.print("No final plan to accept", LogOptions(color=Config.colors["yellow"]))
            return ""

        final_plan = session["final_plan"]

        self.app.message_history.add_user_message(f"Council feedback: {final_plan}")

        LogUtils.print("Council plan injected into conversation", LogOptions(color=Config.colors["green"]))
        LogUtils.print("AI will now consider this feedback", LogOptions(color=Config.colors["cyan"]))

        self.service.clear_session()

        return ""

    def clear_session(self) -> str:
        """Clear current session"""
        self.service.clear_session()
        return ""

    def list_members(self) -> str:
        """List available council members"""
        council_dir = self.service.get_council_directory()

        if not council_dir:
            LogUtils.error("Council directory not found")
            LogUtils.print("Create either:", LogOptions(color=Config.colors["dim"]))
            LogUtils.print("  - .aicoder/council/ (project-specific)", LogOptions(color=Config.colors["dim"]))
            LogUtils.print("  - ~/.config/aicoder-v3/council/ (global)", LogOptions(color=Config.colors["dim"]))
            return ""

        files = os.listdir(council_dir)
        sorted_files = self.service.natural_sort(files)
        member_files = [f for f in sorted_files if f.endswith(".txt") and "moderator" not in f.lower()]

        LogUtils.print("Council Members:", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print("", LogOptions(color=Config.colors["white"]))
        LogUtils.print(f"Directory: {council_dir}", LogOptions(color=Config.colors["yellow"]))
        LogUtils.print("", LogOptions(color=Config.colors["white"]))

        if member_files:
            LogUtils.print("Members:", LogOptions(color=Config.colors["blue"]))
            for idx, member_file in enumerate(member_files, 1):
                name = member_file.replace(".txt", "")
                is_disabled = name.startswith("_")
                color = Config.colors["dim"] if is_disabled else Config.colors["white"]
                status = " (disabled)" if is_disabled else ""
                LogUtils.print(f"  {idx}) {name}{status}", LogOptions(color=color))

        if any("moderator" in f.lower() for f in sorted_files):
            LogUtils.print("", LogOptions(color=Config.colors["white"]))
            LogUtils.print("Moderator (always included):", LogOptions(color=Config.colors["green"]))
            LogUtils.print("  - moderator", LogOptions(color=Config.colors["white"]))

        return ""

    def edit_member(self, args: List[str]) -> str:
        """Edit council member file"""
        if not args:
            LogUtils.print("Usage: /council edit <number|name>", LogOptions(color=Config.colors["yellow"]))
            return ""

        identifier = args[0]
        council_dir = self.service.get_council_directory()

        if not council_dir:
            LogUtils.error("Council directory not found")
            return ""

        files = os.listdir(council_dir)
        sorted_files = self.service.natural_sort(files)
        member_files = [f for f in sorted_files if f.endswith(".txt") and "moderator" not in f.lower()]

        target_file = None
        try:
            num = int(identifier)
            if 1 <= num <= len(member_files):
                target_file = member_files[num - 1]
        except ValueError:
            for f in member_files:
                name = f.replace(".txt", "")
                if identifier.lower() in name.lower():
                    target_file = f
                    break

        if not target_file:
            LogUtils.error(f"Member not found: {identifier}")
            return ""

        editor = os.getenv("EDITOR", "vim")
        filepath = os.path.join(council_dir, target_file)
        os.system(f"{editor} {filepath}")
        LogUtils.print(f"Edited: {target_file}", LogOptions(color=Config.colors["green"]))

        return ""

    def toggle_member(self, args: List[str], enabled: bool) -> str:
        """Enable or disable council member"""
        if not args:
            LogUtils.print(f"Usage: /council {'enable' if enabled else 'disable'} <number|name>", LogOptions(color=Config.colors["yellow"]))
            return ""

        identifier = args[0]
        council_dir = self.service.get_council_directory()

        if not council_dir:
            LogUtils.error("Council directory not found")
            return ""

        files = os.listdir(council_dir)
        sorted_files = self.service.natural_sort(files)
        member_files = [f for f in sorted_files if f.endswith(".txt") and "moderator" not in f.lower()]

        target_file = None
        try:
            num = int(identifier)
            if 1 <= num <= len(member_files):
                target_file = member_files[num - 1]
        except ValueError:
            for f in member_files:
                name = f.replace(".txt", "")
                if identifier.lower() in name.lower():
                    target_file = f
                    break

        if not target_file:
            LogUtils.error(f"Member not found: {identifier}")
            return ""

        filepath = os.path.join(council_dir, target_file)

        if enabled:
            new_name = target_file.lstrip("_")
            new_filepath = os.path.join(council_dir, new_name)
            if new_filepath != filepath:
                os.rename(filepath, new_filepath)
                LogUtils.print(f"Enabled: {new_name}", LogOptions(color=Config.colors["green"]))
        else:
            new_name = f"_{target_file}" if not target_file.startswith("_") else target_file
            new_filepath = os.path.join(council_dir, new_name)
            if new_filepath != filepath:
                os.rename(filepath, new_filepath)
                LogUtils.print(f"Disabled: {new_name}", LogOptions(color=Config.colors["yellow"]))

        return ""

    def toggle_prompt_append(self, args: List[str]) -> str:
        """Toggle prompt append on/off"""
        if not args:
            status = "enabled" if CouncilService.is_prompt_append_enabled() else "disabled"
            LogUtils.print(f"Prompt append is currently {status}", LogOptions(color=Config.colors["cyan"]))
            return ""

        action = args[0].lower()
        if action in ["on", "enable", "1", "true"]:
            CouncilService.enable_prompt_append()
        elif action in ["off", "disable", "0", "false"]:
            CouncilService.disable_prompt_append()
        else:
            LogUtils.print("Usage: /council prompt-append on|off (enable|disable)", LogOptions(color=Config.colors["yellow"]))
            return ""

        return ""

    def cancel(self, args_str: str = "") -> str:
        """Cancel council session and clear all state"""
        # Clear any active session
        self.service.clear_session()

        # Disable auto-council if active
        if CouncilService._auto_council_enabled:
            self.service.disable_auto_council()

        # Clear the spec
        CouncilService.clear_spec()

        LogUtils.print("Council cancelled. All state cleared.", LogOptions(color=Config.colors["yellow"]))
        return ""

    def show_help(self) -> str:
        """Show help message"""
        council_dir = self.service.get_council_directory()

        council_dir_path = council_dir if council_dir else "Not found"

        help_text = f"""
Council Command Help:

Usage:
  /council <message>                              Get opinions from all members
  /council --direct <message>                     Direct opinions (no moderator)
  /council --members member1,member2 <message>    Specific members
  /council --auto                                 Open editor to create spec
  /council --auto <spec.md>                        Auto-iterate with spec file
  /council --auto "text message"                   Auto-iterate with text spec
  /council --auto --reset-context <spec.md>        Fresh context each turn
  /council --auto --no-reset <spec.md>             Preserve context
  /council current                                 Show current council plan
  /council accept                                  Accept and inject plan
  /council clear                                   Clear current session
  /council cancel                                  Cancel council and clear all state
  /council list                                    Show available members
  /council edit <number|name>                      Edit member file
  /council enable <number|name>                    Enable member
  /council disable <number|name>                   Disable member
  /council prompt-append on|off                    Toggle prompt append
  /council help                                    Show this help

Council Directory:
  {council_dir_path}

Environment Variables:
  COUNCIL_DISABLE_PROMPT_APPEND=1                 Disable prompt append at startup

Member files should be named:
  member_name_auto.txt, member_name.txt
  moderator.txt (always included)

Auto-Mode:
  Use --auto flag to enable auto-council
  Council members vote: IMPLEMENTATION_FINISHED or NOT_FINISHED
  Unanimous FINISHED = task complete
  Any NOT_FINISHED = continue with feedback

Prompt Append:
  Controls whether generic instructions are appended to council member prompts
  Can be controlled via: /council prompt-append on|off
  Or via environment variable: COUNCIL_DISABLE_PROMPT_APPEND=1
"""

        LogUtils.print(help_text)
        return ""


def create_plugin(ctx):
    """Council plugin"""

    council_service = CouncilService(ctx.app)
    council_command = CouncilCommand(council_service, ctx.app)

    ctx.register_command("/council", council_command.handle, "Get expert opinions on current work")
    ctx.register_command("/council-cancel", lambda args: council_command.cancel(args), "Cancel council and clear all state")

    def after_ai_processing_hook(has_tool_calls: bool) -> Optional[str]:
        return council_service.handle_auto_council_trigger(has_tool_calls)

    ctx.register_hook("after_ai_processing", after_ai_processing_hook)

    if Config.debug():
        LogUtils.print("[+] Council plugin loaded")
        LogUtils.print("  - /council command")
        LogUtils.print("  - /council-cancel command")
        LogUtils.print("  - Auto-council support")

    return {"cleanup": council_service.cleanup}
