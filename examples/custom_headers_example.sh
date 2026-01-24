#!/bin/bash
# Example: Using custom HTTP headers and streaming control with AI Coder

# Set custom headers - each line should be in "Header-Name: Header-Value" format
export AICODER_HTTP_HEADERS="X-API-Version: v1
X-Custom-Header: my-custom-value
X-Client-ID: my-app-identifier"

# Control streaming behavior (optional)
# Uncomment to disable streaming for APIs that don't support it
# export AICODER_STREAM=0

# Your existing AI Coder configuration
export API_BASE_URL="https://your-api-provider.com/v1"
export API_KEY="your-api-key-here"
export API_MODEL="your-model-name"

# Run AI Coder - it will send the custom headers with every API request
python -m aicoder

# Example usage scenarios:
# 1. API versioning: X-API-Version: v1
# 2. Authentication: X-Custom-Auth: token123  
# 3. Request tracing: X-Request-ID: unique-id
# 4. Client identification: X-Client-ID: my-app
# 5. Rate limiting bypass: X-Bypass-Rate-Limit: true

# Headers are added in this order of precedence:
# 1. Built-in headers (Content-Type, Accept, User-Agent)
# 2. API key header (Authorization: Bearer <key>) if API_KEY is set
# 3. Custom headers from AICODER_HTTP_HEADERS (can override built-ins)

# Format notes:
# - Each header on a new line
# - Header name and value separated by colon (:)
# - Whitespace around names/values is trimmed
# - Invalid lines (missing colon, empty values) are ignored
# - Later headers override earlier ones with same name