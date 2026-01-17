"""
Ralph Plugin - Self-referential AI loops for iterative development

Simple loop where the same prompt is fed repeatedly until completion.
The AI sees its previous work in files and git history, allowing self-correction.
"""

import re
from typing import Optional

from aicoder.utils.log import LogUtils, LogOptions
from aicoder.core.config import Config


class RalphService:
    """Ralph Wiggum loop service - simple self-referential iteration"""

    # Static loop state (persists across sessions)
    _active: bool = False
    _prompt: str = ""
    _completion_promise: str = "DONE"
    _max_iterations: int = 0
    _iteration: int = 0

    @classmethod
    def is_active(cls) -> bool:
        """Check if Ralph loop is active"""
        return cls._active

    @classmethod
    def start_loop(
        cls,
        prompt: str,
        completion_promise: Optional[str] = None,
        max_iterations: int = 10
    ) -> None:
        """Start Ralph loop"""
        cls._active = True
        cls._prompt = prompt
        cls._completion_promise = completion_promise or "DONE"
        cls._max_iterations = max_iterations
        cls._iteration = 1

    @classmethod
    def stop_loop(cls) -> None:
        """Stop Ralph loop"""
        cls._active = False
        cls._prompt = ""
        cls._completion_promise = "DONE"
        cls._max_iterations = 0
        cls._iteration = 0

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
  /ralph "prompt" [--max-iterations N] [--completion-promise "TEXT"]

Commands:
  /ralph <prompt>           Start Ralph loop with prompt
  /ralph-cancel             Cancel active Ralph loop

Options:
  --max-iterations N        Stop after N iterations (default: 10)
  --completion-promise TEXT Phrase that signals completion (default: DONE)

How it works:
  1. Run /ralph "Your task description"
  2. AI works on the task
  3. When AI finishes, same prompt is fed back
  4. AI sees its previous work in files/git
  5. Loop repeats until completion promise found or max iterations reached

Completion:
  To stop the loop, the AI must output: <promise>TEXT</promise>
  Default: <promise>IMPLEMENTATION_FINISHED</promise>

Examples:
  /ralph "Build a REST API for todos"
  /ralph "Fix the auth bug" --max-iterations 20
  /ralph "Refactor code" --completion-promise "DONE"
"""

    def handle_ralph(self, args_str: str) -> str:
        """Handle /ralph command"""
        if not args_str.strip():
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
            max_iterations=args["max_iterations"]
        )

        # Show startup message
        max_iter_str = str(args["max_iterations"]) if args["max_iterations"] > 0 else "unlimited"
        promise_str = args["completion_promise"] or "DONE"

        LogUtils.print("🔄 Ralph loop activated!", LogOptions(color=Config.colors["green"]))
        LogUtils.print(f"  Iteration: {RalphService.get_iteration()}", LogOptions(color=Config.colors["white"]))
        LogUtils.print(f"  Max iterations: {max_iter_str}", LogOptions(color=Config.colors["white"]))
        LogUtils.print(f"  Completion promise: {promise_str}", LogOptions(color=Config.colors["white"]))
        LogUtils.print("", LogOptions(color=Config.colors["white"]))
        LogUtils.print("The AI will repeatedly work on the same task until completion.", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print("Each iteration sees previous work in files and git history.", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print(f"To stop: output <promise>{promise_str}</promise>", LogOptions(color=Config.colors["yellow"]))
        LogUtils.print("", LogOptions(color=Config.colors["white"]))

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

⚠️ DO NOT output <promise>{promise}</promise> until the task is TRULY COMPLETE.
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
            "max_iterations": 10
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
            elif part == "--completion-promise" and i + 1 < len(parts):
                result["completion_promise"] = parts[i + 1]
                i += 2
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
            LogUtils.print("🛑 Ralph loop: Max iterations reached", LogOptions(color=Config.colors["yellow"]))
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

        # Check for completion promise
        if RalphService.check_completion_promise(last_assistant_msg):
            LogUtils.print(f"✅ Ralph loop: Completion promise detected: {RalphService._completion_promise}", LogOptions(color=Config.colors["green"]))
            RalphService.stop_loop()
            return None

        # Continue loop - increment iteration and set next prompt
        RalphService.increment_iteration()
        base_prompt = RalphService.get_prompt()

        # Rebuild prompt with instructions for next iteration
        prompt_with_instructions = self._build_prompt_with_instructions(base_prompt)

        LogUtils.print(f"🔄 Ralph iteration {RalphService.get_iteration()}", LogOptions(color=Config.colors["cyan"]))
        LogUtils.print(f"  Prompt: {base_prompt[:80]}{'...' if len(base_prompt) > 80 else ''}", LogOptions(color=Config.colors["white"]))

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
        LogUtils.print("[+] Ralph plugin loaded", LogOptions(color=Config.colors["green"]))
    return {}
