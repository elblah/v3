"""
Ralph Plugin - Self-referential AI loops for iterative development

Simple loop where the same prompt is fed repeatedly until completion.
The AI sees its previous work in files and git history, allowing self-correction.
"""

import re
from typing import Optional

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


class RalphService:
    """Ralph Wiggum loop service - simple self-referential iteration"""

    # Static loop state (persists across sessions)
    _active: bool = False
    _prompt: str = ""
    _completion_promise: str = "DONE"
    _max_iterations: int = 0
    _iteration: int = 0
    _continuous: bool = False
    _reset_context: bool = False
    _system_prompt: Optional[str] = None

    @classmethod
    def is_active(cls) -> bool:
        """Check if Ralph loop is active"""
        return cls._active

    @classmethod
    def start_loop(
        cls,
        prompt: str,
        completion_promise: Optional[str] = None,
        max_iterations: int = 10,
        continuous: bool = False,
        reset_context: bool = False,
        system_prompt: Optional[str] = None
    ) -> None:
        """Start Ralph loop"""
        cls._active = True
        cls._prompt = prompt
        cls._completion_promise = completion_promise or "DONE"
        cls._max_iterations = max_iterations
        cls._iteration = 1
        cls._continuous = continuous
        cls._reset_context = reset_context
        cls._system_prompt = system_prompt

    @classmethod
    def stop_loop(cls) -> None:
        """Stop Ralph loop"""
        cls._active = False
        cls._prompt = ""
        cls._completion_promise = "DONE"
        cls._max_iterations = 0
        cls._iteration = 0
        cls._continuous = False

    @classmethod
    def get_prompt(cls) -> str:
        """Get current prompt"""
        return cls._prompt

    @classmethod
    def get_iteration(cls) -> int:
        """Get current iteration"""
        return cls._iteration

    @classmethod
    def increment_iteration(cls) -> None:
        """Increment iteration counter"""
        cls._iteration += 1

    @classmethod
    def check_completion_promise(cls, text: str) -> bool:
        """Check if completion promise is in text (format: <promise>TEXT</promise>)"""
        pattern = r"<promise>\s*([^<]+)\s*</promise>"
        matches = re.findall(pattern, text, re.IGNORECASE)

        for match in matches:
            # Strip whitespace and compare
            if match.strip() == cls._completion_promise:
                return True

        return False

    @classmethod
    def should_continue(cls) -> bool:
        """Check if loop should continue (not at max iterations)"""
        if cls._max_iterations == 0:
            return True
        return cls._iteration < cls._max_iterations

    @classmethod
    def is_continuous(cls) -> bool:
        """Check if continuous mode is enabled (ignore promise)"""
        return cls._continuous

    @classmethod
    def should_reset_context(cls) -> bool:
        """Check if context should be reset each iteration"""
        return cls._reset_context

    @classmethod
    def get_system_prompt(cls) -> Optional[str]:
        """Get cached system prompt"""
        return cls._system_prompt


class RalphCommand:
    """Ralph command handler"""

    def __init__(self, app):
        self.app = app
        self.service = RalphService()

    def show_help(self) -> str:
        """Show Ralph help"""
        return """
Ralph Plugin - Self-referential AI loops

Usage:
  /ralph "prompt" [--max-iterations N] [--forever] [--continuous] [--completion-promise "TEXT"] [--reset-context]

Commands:
  /ralph <prompt>           Start Ralph loop with prompt
  /ralph-cancel             Cancel active Ralph loop
  /ralph help               Show this help

Options:
  --max-iterations N        Stop after N iterations (default: 10)
  --forever                 Run forever (equivalent to --max-iterations 0)
  --continuous              Loop until max iterations, ignore completion promise
  --completion-promise TEXT Phrase that signals completion (default: DONE)
  --reset-context           Reset context each iteration (fresh start each time)

How it works:
  1. Run /ralph "Your task description"
  2. AI works on the task
  3. When AI finishes, same prompt is fed back
  4. AI sees its previous work in files/git
  5. Loop repeats until completion promise found or max iterations reached

With --reset-context:
  - Each iteration starts fresh (system prompt + user prompt only)
  - Conversation history is cleared each turn
  - AI relies on files and git history instead of memory
  - Better for focused, independent iterations

Completion:
  To stop the loop, the AI must output: <promise>TEXT</promise>
  Default: <promise>IMPLEMENTATION_FINISHED</promise>
  (Use --continuous to ignore the promise and loop until max iterations)

Examples:
  /ralph "Build a REST API for todos"
  /ralph "Fix the auth bug" --max-iterations 20
  /ralph "Refactor code" --forever
  /ralph "Improve test coverage" --continuous --max-iterations 20
  /ralph "Analyze this codebase" --reset-context
"""

    def handle_ralph(self, args_str: str) -> str:
        """Handle /ralph command"""
        if not args_str.strip() or args_str.strip().lower() == "help":
            return self.show_help()

        # Parse arguments
        args = self._parse_args(args_str)

        if not args["prompt"]:
            LogUtils.error("No prompt provided")
            return "Error: Prompt is required. Use /ralph \"your prompt\""

        # Start loop
        RalphService.start_loop(
            prompt=args["prompt"],
            completion_promise=args["completion_promise"],
            max_iterations=args["max_iterations"],
            continuous=args["continuous"],
            reset_context=args["reset_context"]
        )

        # Show startup message
        max_iter_str = str(args["max_iterations"]) if args["max_iterations"] > 0 else "unlimited"
        promise_str = args["completion_promise"] or "DONE"

        LogUtils.success("Ralph loop activated!")
        LogUtils.info(f"  Iteration: {RalphService.get_iteration()}")
        LogUtils.info(f"  Max iterations: {max_iter_str}")
        LogUtils.info(f"  Completion promise: {promise_str}")
        if args["continuous"]:
            LogUtils.warn("  Mode: continuous (ignores promise)")
        if args["reset_context"]:
            LogUtils.info("  Mode: reset-context (fresh start each iteration)")
        LogUtils.print()
        LogUtils.info("The AI will repeatedly work on the same task until completion.")
        LogUtils.info("Each iteration sees previous work in files and git history.")
        if args["reset_context"]:
            LogUtils.dim("  (context cleared each iteration - fresh start)")
        if args["continuous"]:
            LogUtils.warn("  (ignores <promise> - loops until max iterations)")
        else:
            LogUtils.warn(f"To stop: output <{{promise}}>{promise_str}</{{promise}}>")
        LogUtils.print()

        # Build full prompt with completion instructions for AI
        prompt_with_instructions = self._build_prompt_with_instructions(args["prompt"])

        # Set next prompt to trigger AI
        self.app.set_next_prompt(prompt_with_instructions)

        return ""

    def handle_cancel(self, args_str: str) -> str:
        """Handle /ralph-cancel command"""
        if not RalphService.is_active():
            return "No active Ralph loop to cancel."

        RalphService.stop_loop()
        return "Ralph loop cancelled."

    def _build_prompt_with_instructions(self, base_prompt: str) -> str:
        """Build prompt with completion promise instructions for AI"""
        promise = RalphService._completion_promise
        max_iter = RalphService._max_iterations

        instructions = f"""
---

CRITICAL RALPH LOOP INSTRUCTIONS:

This task will be repeated in a self-referential loop. Each iteration, you will see your previous work in files and git history.

HOW TO SIGNAL COMPLETION:
Your FINAL message must end with this exact line:
<promise>{promise}</promise>

This is REQUIRED to stop the loop. Do not output this unless the task is COMPLETE.

TASK COMPLETION CRITERIA:
- The task is fully implemented and working
- All tests pass (if applicable)
- All requirements are met
- Code is production-ready

WARNING: DO NOT output <promise>{promise}</promise> until the task is TRULY COMPLETE.
The loop will continue indefinitely until this phrase is detected.

{f'MAX ITERATIONS: {max_iter}' if max_iter > 0 else 'MAX ITERATIONS: unlimited'}

---

{base_prompt}
"""
        return instructions

    def _parse_args(self, args_str: str) -> dict:
        """Parse Ralph command arguments"""
        result = {
            "prompt": "",
            "completion_promise": None,
            "max_iterations": 10,
            "continuous": False,
            "reset_context": False
        }

        parts = args_str.split()
        prompt_parts = []
        i = 0

        while i < len(parts):
            part = parts[i]

            if part == "--max-iterations" and i + 1 < len(parts):
                try:
                    result["max_iterations"] = int(parts[i + 1])
                    i += 2
                except ValueError:
                    LogUtils.error("Invalid --max-iterations value")
                    i += 2
            elif part == "--forever":
                result["max_iterations"] = 0
                i += 1
            elif part == "--continuous":
                result["continuous"] = True
                i += 1
            elif part == "--completion-promise" and i + 1 < len(parts):
                result["completion_promise"] = parts[i + 1]
                i += 2
            elif part == "--reset-context":
                result["reset_context"] = True
                i += 1
            else:
                # Part of prompt
                prompt_parts.append(part)
                i += 1

        result["prompt"] = " ".join(prompt_parts)
        return result

    def handle_ralph_trigger(self, has_tool_calls: bool) -> Optional[str]:
        """Hook called after AI processing - trigger next Ralph iteration"""
        if not RalphService.is_active():
            return None

        # Only trigger when AI is done (no tool calls)
        if has_tool_calls:
            return None

        # Check max iterations
        if not RalphService.should_continue():
            LogUtils.warn("Ralph loop: Max iterations reached")
            RalphService.stop_loop()
            return None

        # Get last AI message to check for completion promise
        if not self.app.message_history:
            RalphService.stop_loop()
            return None

        messages = self.app.message_history.get_messages()
        last_assistant_msg = None

        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if content:
                    last_assistant_msg = content
                    break

        if not last_assistant_msg:
            RalphService.stop_loop()
            return None

        # Check for completion promise (skip in continuous mode)
        if not RalphService.is_continuous() and RalphService.check_completion_promise(last_assistant_msg):
            LogUtils.success(f"Ralph loop: Completion promise detected: {RalphService._completion_promise}")
            RalphService.stop_loop()
            return None

        # Continue loop - increment iteration
        RalphService.increment_iteration()
        base_prompt = RalphService.get_prompt()

        LogUtils.info(f"Ralph iteration {RalphService.get_iteration()}")

        # If reset-context is enabled, clear and rebuild context fresh
        if RalphService.should_reset_context():
            LogUtils.dim("  (resetting context)")

            # Reset message history (preserves system prompt, clears chat)
            self.app.message_history.clear()

            # Build fresh prompt with instructions
            prompt_with_instructions = self._build_prompt_with_instructions(base_prompt)

            # Add user message to fresh context
            self.app.message_history.add_user_message(prompt_with_instructions)

            # Return prompt for next AI call
            return prompt_with_instructions

        # Normal mode: just continue with accumulated context
        LogUtils.dim(f"  Prompt: {base_prompt[:80]}{'...' if len(base_prompt) > 80 else ''}")

        # Rebuild prompt with instructions for next iteration
        prompt_with_instructions = self._build_prompt_with_instructions(base_prompt)

        # Set next prompt to trigger AI again
        return prompt_with_instructions


def create_plugin(ctx):
    """Ralph plugin"""
    cmd = RalphCommand(ctx.app)

    # Register commands
    ctx.register_command("/ralph", lambda args: cmd.handle_ralph(args))
    ctx.register_command("/ralph-cancel", lambda args: cmd.handle_cancel(args))

    # Register hook for auto-loop trigger
    ctx.register_hook("after_ai_processing", cmd.handle_ralph_trigger)

    if Config.debug():
        LogUtils.print("[+] Ralph plugin loaded")
    return {}
