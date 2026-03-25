"""
Filter plugin to remove <think>...</think> blocks from streamed AI responses

Minimalist approach: strip everything between <think> and </think> tags.
"""

import sys
from aicoder.core.config import Config


def create_plugin(ctx):
    """Plugin entry point"""
    
    # State that persists across stream chunks
    state = {
        "in_think_block": False,
        "buffer": "",
        "thinking_printed": False,
    }
    
    # Keep reference to original method
    original_method = None
    
    def filter_content(content: str) -> str:
        """Filter content, removing think blocks"""
        if not content:
            return content
        
        result = []
        
        # Add any buffered content from previous chunk
        if state["buffer"]:
            content = state["buffer"] + content
            state["buffer"] = ""
        
        for char in content:
            if state["in_think_block"]:
                # Look for </think>
                state["buffer"] += char
                if state["buffer"].endswith("</think>"):
                    # Clear the "thinking..." line before showing real content
                    sys.stdout.write("\r\x1b[K")  # Carriage return + clear to end of line
                    sys.stdout.flush()
                    state["in_think_block"] = False
                    state["buffer"] = ""
                    state["thinking_printed"] = False
                continue
            
            # Not in think block - check for <think
            state["buffer"] += char
            
            if state["buffer"] == "<think":
                state["in_think_block"] = True
                state["buffer"] = ""
                # Print "thinking..." in dim color
                if not state["thinking_printed"]:
                    sys.stdout.write(f"{Config.colors['dim']}thinking...{Config.colors['reset']}")
                    sys.stdout.flush()
                    state["thinking_printed"] = True
                continue
            
            # Check if buffer could still become <think
            if len(state["buffer"]) < 6 and "<think".startswith(state["buffer"]):
                continue
            
            # Output buffer and clear
            result.append(state["buffer"])
            state["buffer"] = ""
        
        return "".join(result)
    
    def patched_method(self, content: str) -> str:
        """Patched version of print_with_colorization"""
        filtered = filter_content(content)
        return original_method(self, filtered)
    
    def apply_patch():
        """Apply the monkey patch"""
        nonlocal original_method
        from aicoder.core.markdown_colorizer import MarkdownColorizer
        original_method = MarkdownColorizer.print_with_colorization
        MarkdownColorizer.print_with_colorization = patched_method
    
    def remove_patch():
        """Remove the monkey patch"""
        nonlocal original_method
        if original_method:
            from aicoder.core.markdown_colorizer import MarkdownColorizer
            MarkdownColorizer.print_with_colorization = original_method
    
    # Apply patch when plugin loads
    apply_patch()
    
    # Register cleanup
    ctx.register_hook("on_cleanup", remove_patch)
    
    return {
        "name": "filter_thinking",
        "description": "Removes <think>...</think> blocks from AI responses"
    }
