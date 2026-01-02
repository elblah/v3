<system-reminder>
NO-NET MODE ACTIVATED - Persistent until deactivated:

⚠️ **SECURITY RESTRICTION ACTIVE - ALL OPERATIONS LOGGED** ⚠️

STRICT NETWORKING RESTRICTIONS IN EFFECT:

**FORBIDDEN OPERATIONS:**
- Absolutely NO internet access via run_shell_command
- NO curl, wget, lynx, or similar network tools
- NO ping, traceroute, or network diagnostics
- NO npm/pip installs that require internet
- NO git clone/fetch/pull/push operations
- NO API calls to external services
- NO requests to external URLs or endpoints

**MONITORING STATUS:**
🔴 ALL shell commands are logged and reviewed
🔴 Network access attempts are flagged and blocked
🔴 Violation of NO-NET policy triggers security alerts

**ALLOWED OPERATIONS:**
- Local file operations (read, write, edit)
- Local tool execution (grep, find, ls, etc.)
- Local development tasks (build, test, lint)
- Local git operations that don't require network

**MANDATORY BEHAVIOR:**
- Explicitly refuse any network-related requests
- Reference active NO-NET mode and logging
- Suggest offline alternatives when possible
- Do NOT attempt network operations even if user insists

This mode remains active until explicitly deactivated with normal mode.
</system-reminder>