"""
Web Search Plugin - Ultra-fast using DuckDuckGo and lynx

Tools:
- web_search: Search to web
- get_url_content: Fetch URL content
"""

import urllib.request
import urllib.parse
import subprocess
from typing import Dict, Any

from aicoder.core.config import Config


def create_plugin(ctx):
    """Web search and URL content plugin"""

    DEFAULT_LINES_PER_PAGE = 150

    def validate_url(url: str) -> bool:
        """Basic URL validation"""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    def fetch_url_text(url: str, lines: int = DEFAULT_LINES_PER_PAGE) -> str:
        """Fetch URL text using lynx browser with user agent"""
        try:
            # Check if lynx exists
            subprocess.run(["which", "lynx"], capture_output=True, check=True)
        except:
            return "Error: lynx browser not installed. Install with: sudo apt install lynx"

        try:
            # Use lynx with user agent to avoid DuckDuckGo blocking (error 4458)
            # User agent makes it look like a regular browser
            result = subprocess.run(
                ["lynx", "-dump", "-useragent=Mozilla/5.0", url],
                capture_output=True,
                text=True,
                timeout=30
            )
            output_lines = result.stdout.split("\n")[:lines]
            return "\n".join(output_lines)
        except subprocess.TimeoutExpired:
            return "Error: Request timed out after 30 seconds"
        except Exception as e:
            return f"Error fetching URL: {e}"

    def web_search(args: Dict[str, Any]) -> Dict[str, Any]:
        """Search to web using DuckDuckGo"""
        query = args.get("query", "").strip()
        if not query:
            return {
                "tool": "web_search",
                "friendly": "Error: Query cannot be empty",
                "detailed": "Query cannot be empty",
            }

        try:
            encoded = urllib.parse.quote_plus(query)
            search_url = f"https://lite.duckduckgo.com/lite/?q={encoded}"
            content = fetch_url_text(search_url, DEFAULT_LINES_PER_PAGE)

            return {
                "tool": "web_search",
                "friendly": f"Web search for '{query}'",
                "detailed": f"Web search results:\n\n{content}",
            }
        except Exception as e:
            return {
                "tool": "web_search",
                "friendly": f"Error searching web: {e}",
                "detailed": f"Error: {e}",
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
        print("  - web_search tool (auto-approved)")
        print("  - get_url_content tool")
