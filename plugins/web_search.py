"""
Web Search Plugin - Ultra-fast using search providers and lynx

Tools:
- web_search: Search to web
- get_url_content: Fetch URL using lynx -dump (plain text, not raw HTML)

Environment Variables:
- WEB_SEARCH_PROVIDERS: Semicolon-separated list of search providers
  Format: "ProviderName,URL;Provider2Name,URL2;"
  The URL should include the query parameter placeholder, the plugin appends the encoded query
  Default: DuckDuckGo only
"""

import os
import time
from typing import Dict, Any, Tuple

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

_urllib_parse = None
def _get_urllib():
    global _urllib_parse
    if _urllib_parse is None:
        import urllib.parse
        _urllib_parse = urllib.parse
    return _urllib_parse


def create_plugin(ctx):
    """Web search and URL content plugin"""

    DEFAULT_LINES_PER_PAGE = 150

    # In-memory cache to avoid repeated requests
    _cache: Dict[str, str] = {}
    _provider_index = 0
    _last_search_time = 0.0
    SEARCH_COOLDOWN = 180  # 3 minutes - reset to preferred provider after this

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
            result = _get_urllib().urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    # Generic blocking indicators - provider-agnostic
    BLOCKING_INDICATORS = (
        "error-lite@duckduckgo.com",  # DDG specific error
        "Too Many Requests",  # Rate limit response
        "Please complete the following challenge",  # CAPTCHA/challenge page
        "verify you are human",
        "Please solve the challenge below to continue",
        "Access denied",
        "Too many requests",
        "Your request has been flagged",
        "captcha for you",
        "your network appears to be sending automated queries",
        "If this persists, please [1]email us.",
        "Our support email address includes an anonymized error code that helps",
        "Error getting results",
        "Our system has detected the type of high-volume traffic",
        "bots and scrapers",
        "please enter in the characters you see",
        "Why am I seeing CAPTCHA?",
        "Have trouble reading the CAPTCHA?",
    )

    def detect_blocking(content: str) -> bool:
        """Detect if search provider is blocking/banning the request"""
        return any(indicator in content for indicator in BLOCKING_INDICATORS)

    def fetch_url_text(url: str, user_agent: str = None) -> str:
        """Fetch URL text using lynx browser with user agent"""
        import shutil
        if not shutil.which("lynx"):
            return "Error: lynx browser not installed. Install with: sudo apt install lynx"

        import subprocess
        try:
            result = subprocess.run(
                ["lynx", "-dump", "-nolist", url],
                capture_output=True,
                text=True,
                timeout=30
            )
            content = result.stdout

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

    def fetch_url_raw(url: str) -> str:
        """Fetch raw HTML content using urllib"""
        import urllib.request
        MAX_HTML_SIZE = 5 * 1024 * 1024  # 5MB limit
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as response:
                # Check content-length if available
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_HTML_SIZE:
                    return f"Error: Response too large ({int(content_length) // (1024*1024)}MB). Max: {MAX_HTML_SIZE // (1024*1024)}MB"

                # Read with size limit
                data = b""
                while True:
                    chunk = response.read(65536)  # 64KB chunks
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > MAX_HTML_SIZE:
                        return f"Error: Response too large (> {MAX_HTML_SIZE // (1024*1024)}MB)"

                # Try to decode as UTF-8, fall back to latin-1
                try:
                    return data.decode("utf-8")
                except UnicodeDecodeError:
                    return data.decode("latin-1")
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

        # Check cache first
        if query in _cache:
            content = _cache[query]
            lines = content.split("\n")[:DEFAULT_LINES_PER_PAGE]
            return {
                "tool": "web_search",
                "friendly": f"Web search for '{query}' (cached)",
                "detailed": f"Web search results:\n\n" + "\n".join(lines),
            }

        # Reset to preferred provider if enough time has passed
        nonlocal _provider_index, _last_search_time
        now = time.time()
        if now - _last_search_time > SEARCH_COOLDOWN:
            _provider_index = 0
        _last_search_time = now

        failed_providers = []
        encoded = _get_urllib().quote_plus(query)
        num_providers = len(SEARCH_PROVIDERS)

        # Rotate through providers starting from last used index
        for i in range(num_providers):
            idx = (_provider_index + i) % num_providers
            provider_name, base_url = SEARCH_PROVIDERS[idx]
            try:
                search_url = base_url + encoded
                content = fetch_url_text(search_url)

                # Check if this provider blocked us - don't cache blocked results
                if detect_blocking(content):
                    failed_providers.append((provider_name, "blocked"))
                    continue

                # Update rotation index and cache successful result
                _provider_index = (idx + 1) % num_providers
                _cache[query] = content
                lines = content.split("\n")[:DEFAULT_LINES_PER_PAGE]
                return {
                    "tool": "web_search",
                    "friendly": f"Web search for '{query}' (via {provider_name})",
                    "detailed": f"Web search results:\n\n" + "\n".join(lines),
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
        raw = args.get("raw", False)

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

        # Cache key includes raw flag
        cache_key = f"{url}?raw={raw}"

        # Check cache first (only for non-raw content)
        if not raw and cache_key in _cache:
            content = _cache[cache_key]
            lines = content.split("\n")
            start_idx = (page - 1) * DEFAULT_LINES_PER_PAGE
            end_idx = page * DEFAULT_LINES_PER_PAGE
            paginated = "\n".join(lines[start_idx:end_idx])
            return {
                "tool": "get_url_content",
                "friendly": f"Fetched {url} (page {page}, cached)",
                "detailed": paginated,
            }

        try:
            if raw:
                content = fetch_url_raw(url)
            else:
                content = fetch_url_text(url, user_agent="Mozilla/5.0")

            # Only cache non-raw content
            if not raw:
                _cache[cache_key] = content

            # Paginate by lines for text, by chars for raw HTML
            if raw:
                # Paginate by character ranges
                chars_per_page = DEFAULT_LINES_PER_PAGE * 80  # ~80 chars per line average
                start_idx = (page - 1) * chars_per_page
                end_idx = page * chars_per_page
                paginated = content[start_idx:end_idx]
            else:
                lines = content.split("\n")
                start_idx = (page - 1) * DEFAULT_LINES_PER_PAGE
                end_idx = page * DEFAULT_LINES_PER_PAGE
                paginated = "\n".join(lines[start_idx:end_idx])

            return {
                "tool": "get_url_content",
                "friendly": f"Fetched {url} (page {page}{', raw HTML' if raw else ''})",
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
        raw = args.get("raw", False)
        raw_str = " (raw HTML)" if raw else " (lynx text)"
        return f"URL: {url}\nPage: {page}{raw_str}"

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
        description="Fetch URL content. Default: lynx -dump (plain text). Set raw=true for raw HTML via urllib.",
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
                },
                "raw": {
                    "type": "boolean",
                    "description": "Fetch raw HTML instead of lynx-processed text (default: false)",
                    "default": False
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
