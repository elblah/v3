"""
Web Search Plugin - Ultra-fast using search providers and lynx

Tools:
- web_search: Search to web
- get_url_content: Fetch URL content

Environment Variables:
- WEB_SEARCH_PROVIDERS: Semicolon-separated list of search providers
  Format: "ProviderName,URL;Provider2Name,URL2;"
  The URL should include the query parameter placeholder, the plugin appends the encoded query
  Default: DuckDuckGo only
"""

import urllib.request
import urllib.parse
import subprocess
import os
from typing import Dict, Any, Tuple

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """Web search and URL content plugin"""

    DEFAULT_LINES_PER_PAGE = 150

    # Parse search providers from environment variable
    # Format: "Name1,URL1;Name2,URL2;"
    DEFAULT_PROVIDER = ("DuckDuckGo", "https://lite.duckduckgo.com/lite/?q=")

    def parse_providers() -> list[Tuple[str, str]]:
        """Parse WEB_SEARCH_PROVIDERS env var into list of (name, url) tuples"""
        providers_str = os.environ.get("WEB_SEARCH_PROVIDERS", "").strip()
        if not providers_str:
            return [DEFAULT_PROVIDER]

        providers = []
        for part in providers_str.split(";"):
            if not part:
                continue
            parts = part.split(",", 1)
            if len(parts) != 2:
                continue
            name, url = parts
            if name and url:
                providers.append((name, url))

        return providers if providers else [DEFAULT_PROVIDER]

    SEARCH_PROVIDERS = parse_providers()

    def validate_url(url: str) -> bool:
        """Basic URL validation"""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    # Generic blocking indicators - provider-agnostic
    BLOCKING_INDICATORS = (
        "error-lite@duckduckgo.com",  # DDG specific error
        "Please complete the following challenge",  # CAPTCHA/challenge page
        "verify you are human",
        "Access denied",
        "Too many requests",
        "Your request has been flagged",
        "captcha for you",
        "your network appears to be sending automated queries",
        "If this persists, please [1]email us.",
        "Our support email address includes an anonymized error code that helps",
        "Error getting results",
    )

    def detect_blocking(content: str) -> bool:
        """Detect if search provider is blocking/banning the request"""
        return any(indicator in content for indicator in BLOCKING_INDICATORS)

    def fetch_url_text(url: str, lines: int = DEFAULT_LINES_PER_PAGE) -> str:
        """Fetch URL text using lynx browser with user agent"""
        try:
            # Check if lynx exists
            subprocess.run(["which", "lynx"], capture_output=True, check=True)
        except:
            return "Error: lynx browser not installed. Install with: sudo apt install lynx"

        try:
            # Use lynx with user agent to avoid bot detection
            result = subprocess.run(
                ["lynx", "-dump", url],
                capture_output=True,
                text=True,
                timeout=30
            )
            output_lines = result.stdout.split("\n")[:lines]
            content = "\n".join(output_lines)

            # Detect if provider is blocking the request
            if detect_blocking(content):
                warning = (
                    "\n"
                    "[!] WARNING: Search provider has blocked this request as bot traffic.\n"
                    "    The AI cannot continue using web search until this is resolved.\n\n"
                )
                content = warning + content

            return content
        except subprocess.TimeoutExpired:
            return "Error: Request timed out after 30 seconds"
        except Exception as e:
            return f"Error fetching URL: {e}"

    def web_search(args: Dict[str, Any]) -> Dict[str, Any]:
        """Search to web using configured providers in order"""
        query = args.get("query", "").strip()
        if not query:
            return {
                "tool": "web_search",
                "friendly": "Error: Query cannot be empty",
                "detailed": "Query cannot be empty",
            }

        failed_providers = []
        encoded = urllib.parse.quote_plus(query)

        for provider_name, base_url in SEARCH_PROVIDERS:
            try:
                search_url = base_url + encoded
                content = fetch_url_text(search_url, DEFAULT_LINES_PER_PAGE)

                # Check if this provider blocked us
                if detect_blocking(content):
                    failed_providers.append((provider_name, "blocked"))
                    continue

                # Success! Return results with provider info
                return {
                    "tool": "web_search",
                    "friendly": f"Web search for '{query}' (via {provider_name})",
                    "detailed": f"Web search results:\n\n{content}",
                }

            except Exception as e:
                failed_providers.append((provider_name, str(e)))

        # All providers failed
        error_details = "\n".join([f"  - {name}: {reason}" for name, reason in failed_providers])
        return {
            "tool": "web_search",
            "friendly": "[!] All search providers failed",
            "detailed": f"Failed to search '{query}'. Tried providers:\n{error_details}",
        }

    def get_url_content(args: Dict[str, Any]) -> Dict[str, Any]:
        """Get URL content"""
        url = args.get("url", "").strip()
        page = args.get("page", 1)

        if not url:
            return {
                "tool": "get_url_content",
                "friendly": "Error: URL cannot be empty",
                "detailed": "URL cannot be empty",
            }

        if not validate_url(url):
            return {
                "tool": "get_url_content",
                "friendly": "Error: Invalid URL format",
                "detailed": "Invalid URL format",
            }

        try:
            content = fetch_url_text(url, DEFAULT_LINES_PER_PAGE * page)
            lines = content.split("\n")
            start_idx = (page - 1) * DEFAULT_LINES_PER_PAGE
            end_idx = page * DEFAULT_LINES_PER_PAGE
            paginated = "\n".join(lines[start_idx:end_idx])

            return {
                "tool": "get_url_content",
                "friendly": f"Fetched {url} (page {page})",
                "detailed": paginated,
            }
        except Exception as e:
            return {
                "tool": "get_url_content",
                "friendly": f"Error fetching URL: {e}",
                "detailed": f"Error: {e}",
            }

    # Format function for get_url_content (shows URL during approval)
    def format_get_url_content(args):
        """Format arguments for get_url_content"""
        url = args.get("url", "")
        page = args.get("page", 1)
        return f"URL: {url}\nPage: {page}"

    # Register web_search tool
    ctx.register_tool(
        name="web_search",
        fn=web_search,
        description="Search to web for information",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string"
                }
            },
            "required": ["query"]
        },
        auto_approved=True
    )

    # Register get_url_content tool with formatArguments
    ctx.register_tool(
        name="get_url_content",
        fn=get_url_content,
        description="Fetch to full text content of a URL (https only)",
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (https only)"
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination (default: 1)",
                    "default": 1
                }
            },
            "required": ["url"]
        },
        auto_approved=False,
        format_arguments=format_get_url_content
    )

    if Config.debug():
        LogUtils.print("  - web_search tool (auto-approved)")
        LogUtils.print("  - get_url_content tool")
