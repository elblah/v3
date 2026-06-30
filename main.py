#!/usr/bin/env python3
"""
AI Coder - Fast, lightweight AI-assisted development that runs anywhere
Main entry point - synchronous version
"""

import sys
import os
import time

# Earliest moment before project code: set AICODER_START_TIME if shell didn't
_AICODER_START_SET_BY_SHELL = "AICODER_START_TIME" in os.environ
if not _AICODER_START_SET_BY_SHELL:
    os.environ["AICODER_START_TIME"] = str(time.time())

from aicoder.core.aicoder import AICoder  # noqa: E402
from aicoder.core.config import Config  # noqa: E402
from aicoder.utils.log import LogUtils, LogOptions  # noqa: E402


def main():
    """Main entry point"""

    # Show startup info
    if Config.debug():
        LogUtils.success("AI Coder starting in debug mode")

    # Create and run AI Coder
    app = AICoder()

    try:
        app.initialize()

        # Calculate and display startup time (only in TTY)
        start_time_str = os.environ.get("AICODER_START_TIME")
        if start_time_str and sys.stdout.isatty():
            try:
                start_time = float(start_time_str)
                current_time = time.time()
                startup_time = current_time - start_time
                label = "total" if _AICODER_START_SET_BY_SHELL else "app loading"
                LogUtils.printc(f"Startup time ({label}): {startup_time:.2f}s", color="brightCyan")
            except ValueError:
                pass

        app.run()
    except KeyboardInterrupt:
        LogUtils.print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        LogUtils.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
