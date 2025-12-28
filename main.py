#!/usr/bin/env python3
"""
AI Coder - Fast, lightweight AI-assisted development that runs anywhere
Main entry point - synchronous version
"""

import sys
import os
import time

from aicoder.core.aicoder import AICoder
from aicoder.core.config import Config
from aicoder.utils.log import success, warn, error


def main():
    """Main entry point"""
    
    # Show startup info
    if Config.debug():
        success("AI Coder starting in debug mode")

    # Create and run AI Coder
    app = AICoder()

    try:
        app.initialize()
        
        # Calculate and display startup time
        start_time_str = os.environ.get("AICODER_START_TIME")
        if start_time_str:
            try:
                # Convert EPOCHREALTIME (seconds.microseconds) to float
                start_time = float(start_time_str)
                current_time = time.time()
                startup_time = current_time - start_time
                print(f"{Config.colors['brightCyan']}Total startup time: {startup_time:.2f} seconds{Config.colors['reset']}")
            except ValueError:
                # If parsing fails, silently ignore
                pass
        
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
