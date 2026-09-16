#!/usr/bin/env bash
# Minimal curl test for OpenCode Zen "union-alpha" (Anthropic messages API).
# Free tier requires opencode client-identification headers, no API key needed.

# OpenCode-format IDs: <12 hex timestamp ms*4096><14 base62>
ocid() {
  local ts
  ts=$(printf '%012x' $(( ( $(date +%s%3N) * 4096 ) & 0xffffffffffff )))
  echo "${ts}$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c14)"
}

session=$(ocid)
request=$(ocid)
# real opencode sends sha1-hex of the project dir (or "global")
project=$(printf '%s' "$PWD" | sha1sum | cut -d' ' -f1)

curl -sS --max-time 120 -w '\nHTTP_STATUS=%{http_code}\n' \
  https://opencode.ai/zen/v1/messages \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -H 'user-agent: opencode/1.0.0' \
  -H "x-opencode-project: $project" \
  -H "x-opencode-session: ses_$session" \
  -H "x-opencode-request: msg_$request" \
  -H "x-opencode-client: cli" \
  -d '{"model":"union-alpha","max_tokens":64,"messages":[{"role":"user","content":"Reply with exactly: hello"}]}'
