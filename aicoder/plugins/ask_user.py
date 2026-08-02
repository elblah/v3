"""
Ask User Plugin - Interactive user input for AI

Allows AI to ask questions and get user selections via fzf.
Supports batching multiple questions in a single tool call.

Tool: ask_user
Args: {
    "questions": [
        {"question": "Which framework?", "options": ["React", "Vue", "Svelte"]},
        {"question": "TypeScript?", "options": ["Yes", "No"]}
    ]
}
Returns: {
    "answers": [
        {"question": "Which framework?", "answer": "React"},
        {"question": "TypeScript?", "answer": "Yes"}
    ]
}

Requires fzf. Window height auto-fits content (capped at 60% of terminal);
--reverse --border=rounded --exact for clean UX.
Long options wrap to the terminal width. Selection times out after
ASK_USER_TIMEOUT seconds (default 60) so the AI never blocks on user input;
timeout or cancel returns control to the AI.
"""

import subprocess
import shutil
import textwrap
import os
from typing import Dict, Any, List

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """Ask User plugin - interactive question/answer for AI"""

    # No controlling terminal = no screen for fzf; it would fail instantly
    try:
        os.close(os.open("/dev/tty", os.O_RDWR))
    except OSError:
        return

    # Check if fzf is available
    if not shutil.which("fzf"):
        LogUtils.warn("[ask_user] fzf not found - plugin disabled")
        LogUtils.print("    Install fzf to enable ask_user tool: https://github.com/junegunn/fzf")
        return

    def wrap_options_for_fzf(options: List[str], max_width: int = 80) -> tuple[List[str], dict]:
        """
        Wrap long options for fzf display.
        Returns (wrapped_options, original_map) where original_map maps first line to original text.
        """
        wrapped_options = []
        original_map = {}
        
        for opt in options:
            if len(opt) <= max_width:
                wrapped_options.append(opt)
                original_map[opt] = opt
            else:
                # Wrap to multiple lines, prefix continuation with "  "
                wrapped_lines = textwrap.wrap(opt, width=max_width, break_long_words=True)
                if wrapped_lines:
                    # First line is the identifier
                    first_line = wrapped_lines[0]
                    # Continuation lines
                    continuation = "\n".join("  " + line for line in wrapped_lines[1:])
                    wrapped_text = first_line if len(wrapped_lines) == 1 else f"{first_line}\n{continuation}"
                    wrapped_options.append(wrapped_text)
                    original_map[first_line] = opt
        
        return wrapped_options, original_map

    def ask_single_question_fzf(question: str, options: List[str], timeout: float) -> tuple:
        """
        Ask question using fzf.

        Returns:
            (answer, "ok") on selection
            (None, "cancelled") if user dismissed (ESC)
            (None, "timeout") if no selection within `timeout` seconds
        """
        try:
            # Print question above fzf (fzf prompt doesn't wrap)
            print(f"\n{question}")
            
            # Wrap long options (get terminal width, default 80)
            try:
                terminal_width = min(os.get_terminal_size().columns - 10, 100)  # Leave some padding
            except OSError:
                terminal_width = 80
            
            wrapped_options, original_map = wrap_options_for_fzf(options, max_width=terminal_width)

            # Height auto-fits content: fzf's ~N% shrink counts ITEMS, not wrapped
            # display lines, so it under-sizes multiline options. Compute the real
            # line count here and cap at 60% of the terminal (+3 = prompt + borders).
            lines_needed = sum(1 + s.count('\n') for s in wrapped_options)
            try:
                term_rows = os.get_terminal_size().lines
            except OSError:
                term_rows = 40
            height = max(min(lines_needed + 3, int(term_rows * 0.6) + 1), 3)
            
            proc = subprocess.Popen(
                [
                    "fzf",
                    "--height", str(height),
                    "--reverse",
                    "--border=rounded",
                    "--exact",  # Exact match, no fuzzy
                    "--no-info",
                    "--prompt", "> ",  # Minimal prompt, question printed above
                    "--read0",  # Use null separator to handle multiline options
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            try:
                out, _ = proc.communicate(input="\0".join(wrapped_options), timeout=timeout)
            except subprocess.TimeoutExpired:
                # SIGTERM lets fzf restore the terminal (SIGKILL would not)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                print(f"\n  → no selection within {timeout:.0f}s (skipped)\n")
                return None, "timeout"
            
            if proc.returncode != 0:
                # User cancelled (ESC)
                return None, "cancelled"
            
            selected = out.strip()
            
            # Extract first line if multiline (it's the identifier)
            if selected:
                first_line = selected.split('\n')[0].strip()
                answer = original_map.get(first_line, first_line)
                
                # Print answer in green with spacing (question already printed above)
                colors = Config.colors
                print(f"\n  → {colors['green']}{answer}{colors['reset']}\n")
                
                return answer, "ok"
            
            return None, "cancelled"
        except Exception as e:
            LogUtils.error(f"fzf error: {e}")
            return None, "cancelled"

    def ask_single_question(question: str, options: List[str]) -> tuple:
        """Ask via fzf with a timeout so the AI never blocks forever on user input."""
        timeout = float(os.environ.get("ASK_USER_TIMEOUT", "60"))
        return ask_single_question_fzf(question, options, timeout)

    def ask_user(args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ask user questions with options
        
        Args:
            questions: List of {"question": str, "options": [str]}
        
        Returns:
            {"answers": [{"question": str, "answer": str}]}
        """
        questions = args.get("questions", [])
        
        if not questions:
            return {
                "tool": "ask_user",
                "friendly": "Error: No questions provided",
                "detailed": "The ask_user tool requires a 'questions' array with at least one question",
            }
        
        # Validate questions structure
        for i, q in enumerate(questions):
            if "question" not in q:
                return {
                    "tool": "ask_user",
                    "friendly": f"Error: Question {i+1} missing 'question' field",
                    "detailed": "Each question must have 'question' and 'options' fields",
                }
            if "options" not in q or not q["options"]:
                return {
                    "tool": "ask_user",
                    "friendly": f"Error: Question {i+1} missing 'options' field or empty options",
                    "detailed": f"Question '{q.get('question', 'unknown')}' needs non-empty 'options' array",
                }
        
        answers = []
        
        for q in questions:
            question = q["question"]
            options = q["options"]

            answer, status = ask_single_question(question, options)

            if status == "timeout":
                return {
                    "tool": "ask_user",
                    "friendly": "Timeout - no response",
                    "detailed": f"No selection within the timeout at question: {question}",
                    "answers": answers,  # Include partial results
                }

            if answer is None:
                return {
                    "tool": "ask_user",
                    "friendly": "User cancelled",
                    "detailed": f"User cancelled at question: {question}",
                    "answers": answers,  # Include partial results
                }
            
            answers.append({
                "question": question,
                "answer": answer
            })
        
        # Format response - minimal since answer already printed in green
        if len(answers) == 1:
            friendly = "✓"
        else:
            friendly = f"✓ {len(answers)} answers"
        
        detailed_lines = ["User responses:"]
        for a in answers:
            detailed_lines.append(f"  • {a['question']}: {a['answer']}")
        
        return {
            "tool": "ask_user",
            "friendly": friendly,
            "detailed": "\n".join(detailed_lines),
            "answers": answers,
        }

    # Register tool
    ctx.register_tool(
        name="ask_user",
        fn=ask_user,
        description="Ask the user multiple-choice questions and return their selections. Use when a decision needs human input: multiple valid approaches exist, the request is ambiguous, or there are significant trade-offs. Do NOT use for trivial or clearly-decidable matters. Each question needs 2-8 short options. Prefer batching up to 3 related questions per call. Selection times out after ASK_USER_TIMEOUT seconds (default 60); timeout or cancel returns with partial answers so the AI can continue (timeout -> friendly='Timeout - no response', cancel -> friendly='User cancelled'). Example: [{'question': 'Which editor?', 'options': ['vim', 'nano', 'emacs']}]",
        parameters={
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question to ask"
                            },
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Available options to choose from"
                            }
                        },
                        "required": ["question", "options"]
                    },
                    "description": "List of questions with options (can batch multiple questions)"
                }
            },
            "required": ["questions"]
        },
        auto_approved=True  # Safe - only reads user input
    )

    if Config.debug():
        LogUtils.print("  - ask_user tool (auto-approved)")
        LogUtils.print("    using fzf (auto-fit height, reverse, exact, auto-wrap, timeout)")
