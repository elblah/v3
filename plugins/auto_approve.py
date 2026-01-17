"""
Auto-Approve Plugin - Auto approve/deny tools based on regex rules

This plugin intercepts the before_approval_prompt hook and returns automatic
decisions based on matching rules against tool names and arguments.

Usage:
    Copy to .aicoder/plugins/auto_approve.py

Rules are defined in .aicoder/auto-approve-rules.json with format:
    [
        {
            "tool": "tool_name_pattern",
            "match": "regex_pattern_for_arguments",
            "decision": true   // true=approve, false=deny
        }
    ]

Example rules (.aicoder/auto-approve-rules.json):
    [
        {"tool": "run_shell_command", "match": "uname", "decision": true},
        {"tool": "run_shell_command", "match": "curl", "decision": false}
    ]

This example:
    - Auto-approves: uname (safe read-only system info)
    - Auto-denies: curl (network operations require approval)
"""

import re
import json
from pathlib import Path

from aicoder.core.config import Config

RULES_FILE = Path(".aicoder/auto-approve-rules.json")


def load_rules():
    """Load rules from JSON file"""
    if RULES_FILE.exists():
        try:
            return json.loads(RULES_FILE.read_text())
        except json.JSONDecodeError as e:
            print(f"[!] Invalid JSON in {RULES_FILE}: {e}")
            return []
    return []


def create_plugin(ctx):
    """Register approval interceptor"""

    def before_approval_prompt(tool_name: str, arguments: dict) -> bool | None:
        """
        Called before approval prompt. Return:
        - True  -> auto-approve
        - False -> auto-deny
        - None  -> ask user
        """
        rules_data = load_rules()
        if not rules_data:
            return None

        # Support both array format and object with "rules" key
        rules = rules_data if isinstance(rules_data, list) else rules_data.get("rules", [])

        # Flatten arguments to string for regex matching
        args_str = json.dumps(arguments, sort_keys=True, default=str)

        for rule in rules:
            # Match tool name (supports regex)
            tool_pattern = rule.get("tool", ".*")
            if not re.match(tool_pattern, tool_name):
                continue

            # Match arguments (supports regex)
            match_pattern = rule.get("match", ".*")
            if not re.search(match_pattern, args_str):
                continue

            # Rule matched - return decision
            decision = rule.get("decision", True)
            decision_str = "approved" if decision else "denied"
            print(f"[auto-{decision_str}] {tool_name}: {rule.get('match', '.*')}")
            return decision

        # No rule matched
        return None

    # Register hook (plugins can return True/False/None)
    ctx.register_hook("before_approval_prompt", before_approval_prompt)

    if Config.debug():
        print("[+] Loaded auto_approve plugin")
        print(f"    Rules file: {RULES_FILE}")
        print("    Copy .aicoder/auto-approve-rules.json.sample to .aicoder/auto-approve-rules.json")
        print("    and edit to define your rules.")
