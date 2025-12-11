#!/usr/bin/env python3
"""
AI Coder - Fast, lightweight AI-assisted development that runs anywhere
Main entry point - synchronous version
"""

import sys
import signal

from aicoder.core.aicoder import AICoder
from aicoder.core.config import Config
from aicoder.utils.log import success, warn, error


# Super simple Ctrl+Z detection test
def handle_ctrl_z(signum, frame):
    print("\nDETECTED CTRL+Z!")
    # Don't actually suspend, just continue
    return


def main():
    """Main entry point"""
    # Setup Ctrl+Z detection
    signal.signal(signal.SIGTSTP, handle_ctrl_z)
    
    # Show startup info
    if Config.debug():
        success("AI Coder starting in debug mode")

    # Create and run AI Coder
    app = AICoder()

    try:
        app.initialize()
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
