"""
Web Search Plugin - Ultra-fast using search providers and lynx

Tools:
- web_search: Search to web
- get_url_content: Fetch URL using lynx -dump (plain text, not raw HTML)

Environment Variables:
- WEB_SEARCH_PROVIDERS: Semicolon-separated list of search providers
  Format: "ProviderName,URL;Provider2Name,URL2;"
  The URL should include the query parameter placeholder, the plugin appends the encoded query
  Default: None (must be configured)
- WEB_SEARCH_SCRIPT: Optional path to a gateway script (e.g. examples/search-gateway).
  If set and resolves to an executable, web_search/get_url_content route through it
  (dtx gobrow, markdown output). If unset/missing, native lynx logic is used.
  Default: None (native behavior)
"""

import os
import shutil
import time
from typing import Dict, Any, Tuple

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.tools.internal.run_shell_command import safe_subprocess_run

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

    # In-memory cache to avoid repeated requests. Values: (last_access, content).
    _cache: Dict[str, Tuple[float, str]] = {}
    _provider_index = 0
    _last_search_time = 0.0
    SEARCH_COOLDOWN = 180  # 3 minutes - reset to preferred provider after this
    CACHE_TTL = 180.0  # seconds since last access before an entry is evicted
    CACHE_MAX_ENTRIES = 32  # LRU evicted when over this many entries
    CACHE_MAX_BYTES = 32 * 1024 * 1024  # ~32MB total (strings, approximate)

    def _cache_get(key: str) -> str:
        """Fresh cached content or None; hit refreshes the access clock."""
        entry = _cache.get(key)
        if entry is None:
            return None
        atime, content = entry
        now = time.time()
        if now - atime > CACHE_TTL:
            del _cache[key]
            return None
        _cache[key] = (now, content)  # sliding window
        return content

    def _cache_set(key: str, content: str) -> None:
        """Store content and LRU-evict until under both caps (keeps >= 1 entry)."""
        _cache[key] = (time.time(), content)
        while len(_cache) > 1:
            total = sum(len(c) for _, c in _cache.values())
            if len(_cache) <= CACHE_MAX_ENTRIES and total <= CACHE_MAX_BYTES:
                break
            victim = min(_cache, key=lambda k: _cache[k][0])
            del _cache[victim]

    # Parse search providers from environment variable
    # Format: "Name1,URL1;Name2,URL2;"
    def parse_providers() -> list[Tuple[str, str]]:
        """Parse WEB_SEARCH_PROVIDERS env var into list of (name, url) tuples"""
        providers_str = os.environ.get("WEB_SEARCH_PROVIDERS", "").strip()
        if not providers_str:
            return None  # Not configured

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

        return providers if providers else None

    SEARCH_PROVIDERS = parse_providers()

    def _search_script_path():
        """Return the WEB_SEARCH_SCRIPT path if configured and usable, else None."""
        script = os.environ.get("WEB_SEARCH_SCRIPT", "").strip()
        if not script:
            return None
        if os.path.isabs(script):
            return script if os.path.exists(script) else None
        found = shutil.which(script)
        return found if found and os.path.exists(found) else None

    def _run_gateway(cmd: str, arg: str, max_tokens: int = 8000):
        """Route through the WEB_SEARCH_SCRIPT gateway if configured.

        Returns stdout text on success, or None when the script is unavailable
        or failed (non-zero exit / exception) so the caller falls back to the
        native lynx path. Empty stdout is treated as failure so a native retry
        can run (e.g. gobrow 403 -> native may also fail, which is fine).
        """
        import subprocess
        script = _search_script_path()
        if not script:
            return None
        try:
            result = subprocess.run(
                [script, cmd, arg, str(max_tokens)],
                capture_output=True,
                text=True,
                timeout=160,
                check=False,
            )
            if result.returncode != 0:
                return None
            return result.stdout
        except Exception:
            return None

    def validate_url(url: str) -> bool:
        """Basic URL validation - only http/https allowed (blocks file:// etc)"""
        try:
            result = _get_urllib().urlparse(url)
            return result.scheme in ("http", "https") and bool(result.netloc)
        except:
            return False

    # Generic blocking indicators - provider-agnostic
    BLOCKING_INDICATORS = (
        "error-lite@",  # DDG specific error
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
            # Use bytes mode and decode manually for better encoding handling
            result = safe_subprocess_run(
                ["lynx", "-dump", "-nolist", url],
                capture_output=True,
                timeout=30,
                requires_net=True,
            )
            # Try UTF-8 first, then latin-1, replace errors
            try:
                content = result.stdout.decode("utf-8", errors="replace")
            except Exception:
                content = result.stdout.decode("latin-1", errors="replace")

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
        """Fetch raw HTML: gorl (preferred) -> curl -> urllib fallback"""
        MAX_HTML_SIZE = 5 * 1024 * 1024  # 5MB limit

        def _finish(data: bytes) -> str:
            if len(data) > MAX_HTML_SIZE:
                return f"Error: Response too large (> {MAX_HTML_SIZE // (1024*1024)}MB)"
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("latin-1")

        # gorl/curl handles HTTP errors with non-zero rc and empty stdout ->
        # fall through to the next fetcher. requires_net=True: refuse when the
        # seal isolates the netns (do NOT leak through to urllib in that case).
        for cmd in (
            ["gorl", url, "-A", "Mozilla/5.0"],
            ["curl", "-fsSL", "-A", "Mozilla/5.0", url],
        ):
            if not shutil.which(cmd[0]):
                continue
            try:
                result = safe_subprocess_run(
                    cmd, capture_output=True, timeout=30, requires_net=True
                )
                if result.returncode == 0:
                    return _finish(result.stdout)
            except Exception as e:
                return f"Error fetching URL: {e}"

        # Last-resort pure-Python fallback (works with no external binary)
        import urllib.request
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

        # Optional gateway (WEB_SEARCH_SCRIPT) — mirrors the vision plugin pattern.
        gw = _run_gateway("search", query)
        if gw is not None:
            lines = gw.split("\n")[:DEFAULT_LINES_PER_PAGE]
            return {
                "tool": "web_search",
                "friendly": f"Web search for '{query}' (gateway)",
                "detailed": "Web search results:\n\n" + "\n".join(lines),
            }

        if SEARCH_PROVIDERS is None:
            example = "WEB_SEARCH_PROVIDERS=MySearch,https://search.example.com/search?q="
            return {
                "tool": "web_search",
                "friendly": "Web search not configured",
                "detailed": (
                    "Plugin not configured. Set the WEB_SEARCH_PROVIDERS environment variable.\n\n"
                    f"Example format:\n  export {example}\n\n"
                    "Format: 'Name,URL;Name2,URL2;' - the URL should include a query parameter placeholder"
                ),
            }

        # Check cache first
        content = _cache_get(query)
        if content is not None:
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
                _cache_set(query, content)
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

        # Optional gateway for text fetch (native path handles raw HTML).
        if not raw:
            gw = _run_gateway("fetch", url)
            if gw is not None:
                return {
                    "tool": "get_url_content",
                    "friendly": f"Fetched {url} (gateway)",
                    "detailed": gw,
                }

        # Cache key includes raw flag
        cache_key = f"{url}?raw={raw}"

        # Check cache first (only for non-raw content)
        content = _cache_get(cache_key) if not raw else None
        if content is not None:
            lines = content.split("\n")
            total = len(lines)
            max_page = (total + DEFAULT_LINES_PER_PAGE - 1) // DEFAULT_LINES_PER_PAGE
            start_idx = (page - 1) * DEFAULT_LINES_PER_PAGE
            end_idx = page * DEFAULT_LINES_PER_PAGE
            paginated = "\n".join(lines[start_idx:end_idx])
            footer = f"\n[page {page}/{max_page}]" + (f" | more: page={min(page+1, max_page)}" if max_page > 1 else "")
            return {
                "tool": "get_url_content",
                "friendly": f"Fetched {url} (page {page}/{max_page}, cached)",
                "detailed": paginated + footer,
            }

        try:
            if raw:
                content = fetch_url_raw(url)
            else:
                content = fetch_url_text(url, user_agent="Mozilla/5.0")

            # Only cache non-raw content
            if not raw:
                _cache_set(cache_key, content)

            # Paginate by lines for text, by chars for raw HTML
            if raw:
                # Paginate by character ranges
                chars_per_page = DEFAULT_LINES_PER_PAGE * 80  # ~80 chars per line average
                total = len(content)
                max_page = (total + chars_per_page - 1) // chars_per_page
                start_idx = (page - 1) * chars_per_page
                end_idx = page * chars_per_page
                paginated = content[start_idx:end_idx]
            else:
                lines = content.split("\n")
                total = len(lines)
                max_page = (total + DEFAULT_LINES_PER_PAGE - 1) // DEFAULT_LINES_PER_PAGE
                start_idx = (page - 1) * DEFAULT_LINES_PER_PAGE
                end_idx = page * DEFAULT_LINES_PER_PAGE
                paginated = "\n".join(lines[start_idx:end_idx])

            footer = f"\n[page {page}/{max_page}]" + (f" | more: page={min(page+1, max_page)}" if max_page > 1 else "")
            return {
                "tool": "get_url_content",
                "friendly": f"Fetched {url} (page {page}/{max_page}{', raw HTML' if raw else ''})",
                "detailed": paginated + footer,
            }
        except Exception as e:
            return {
                "tool": "get_url_content",
                "friendly": f"Error fetching URL: {e}",
                "detailed": f"Error: {e}",
            }

    def _raw_fetcher_label():
        """Raw fetch attempt chain (gorl -> curl -> urllib), per binaries present."""
        avail = [b for b in ("gorl", "curl") if shutil.which(b)]
        if not avail:
            return "urllib"
        return " -> ".join(avail) + " -> urllib"

    # Format function for get_url_content (shows URL during approval)
    def format_get_url_content(args):
        """Format arguments for get_url_content, including gateway mode"""
        url = args.get("url", "")
        page = args.get("page", 1)
        raw = args.get("raw", False)
        raw_str = " (raw HTML)" if raw else " (lynx text)"
        if raw:
            mode = f"native raw HTML ({_raw_fetcher_label()})"
        elif _search_script_path():
            mode = "gateway (WEB_SEARCH_SCRIPT)"
        else:
            mode = "native lynx"
        return f"URL: {url}\nPage: {page}{raw_str}\nMode: {mode}"

    # Format function for web_search (shows query + gateway mode during approval)
    def format_web_search_args(args):
        """Format arguments for web_search, including gateway mode"""
        query = args.get("query", "").strip()
        if _search_script_path():
            mode = "gateway (WEB_SEARCH_SCRIPT)"
        else:
            mode = "native (providers/lynx)"
        return f"Query: {query}\nMode: {mode}"

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
        auto_approved=True,
        format_arguments=format_web_search_args
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
