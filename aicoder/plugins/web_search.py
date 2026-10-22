r"""
Web Search Plugin - Search providers plus pure-stdlib URL fetching

Tools:
- web_search: Search to web
- get_url_content: Fetch a URL as readable text (lynx -dump when available,
  otherwise a stdlib HTML->text fallback) or as raw HTML when raw=true

Environment Variables:
- WEB_SEARCH_PROVIDERS: Semicolon-separated list of search providers
  Format: "ProviderName,URL;Provider2Name,URL2;"
  The URL should include the query parameter placeholder, the plugin appends the encoded query
  Default: None (must be configured)
- WEB_SEARCH_SCRIPT: Optional path to a gateway script (e.g. examples/search-gateway).
  If set and resolves to an executable, web_search/get_url_content route through it
  (dtx gobrow, markdown output). If unset/missing, native logic is used
  (lynx when it can run, otherwise pure-stdlib urllib + HTML->text).
  Default: None (native behavior)
- WEB_SEARCH_URL_ALLOW: Optional allowlist for get_url_content. Newline-separated
  regexes, matched against the full URL with re.search(); a URL is fetched only if
  at least one pattern matches. Blank lines anywhere (leading, trailing, between
  entries) and lines starting with '#' are ignored, so the natural shell form
  works as written:
    export WEB_SEARCH_URL_ALLOW="
    ^https://([a-z0-9-]+\.)*github\.com/
    ^https://raw\.githubusercontent\.com/
    "
  Unset, empty or whitespace-only means no restriction. If the variable is set but
  has no usable regex, every fetch is refused (fail-closed). Patterns are searched
  anywhere in the URL, so anchor them ('^https://host/'); otherwise a URL such as
  https://evil.example/?r=https://github.com/ satisfies the github pattern.
  Default: None (unrestricted)
"""

import os
import re
import shutil
import time
from html.parser import HTMLParser
from typing import Dict, Any, List, Optional, Tuple

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


# ---------------------------------------------------------------------------
# Stdlib-only fetching / HTML-to-text helpers.
#
# These exist so the tools still work where no external binary can be run
# (sandbox blocking execvp, no lynx/gorl/curl installed).
# ---------------------------------------------------------------------------

MAX_HTML_BYTES = 5 * 1024 * 1024  # 5MB
LINK_SCHEMES = ("http://", "https://")


class _HTMLTextExtractor(HTMLParser):
    """Very small HTML -> plain text renderer (no deps, no layout engine)."""

    # Tags that start a new line in the output
    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl",
        "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
        "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p",
        "pre", "section", "table", "tbody", "td", "tfoot", "th", "thead", "title",
        "tr", "ul",
    }
    # Tags whose content is never readable text
    SKIP_TAGS = {
        "canvas", "embed", "iframe", "noscript", "object", "script", "style",
        "svg", "template",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out: List[str] = []
        self._skip = 0
        self._links: List[Tuple[Optional[str], int]] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "a":
            href = (dict(attrs).get("href") or "").strip()
            self._links.append((href if href.startswith(LINK_SCHEMES) else None, len(self._out)))
            return
        if tag == "li":
            self._out.append("\n- ")
        elif tag in self.BLOCK_TAGS:
            self._out.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "a":
            if self._links:
                href, _start = self._links.pop()
                if href:
                    self._out.append(f" <{href}>")
            return
        if tag in self.BLOCK_TAGS:
            self._out.append("\n")

    def handle_data(self, data):
        # Collapse runs of whitespace (including newlines) so wrapped source
        # markup does not leak hard line breaks into the extracted text, but
        # keep a single separating space where the original had any.
        if self._skip or not data:
            return
        collapsed = " ".join(data.split())
        if not collapsed:
            if self._out and not self._out[-1].endswith((" ", "\n")):
                self._out.append(" ")
            return
        if data[0].isspace() and self._out and not self._out[-1].endswith((" ", "\n")):
            collapsed = " " + collapsed
        if data[-1].isspace():
            collapsed += " "
        self._out.append(collapsed)

    def get_text(self) -> str:
        lines = []
        for line in "".join(self._out).splitlines():
            line = " ".join(line.split())
            if line:
                lines.append(line)
        return "\n".join(lines)


def html_to_text(html: str) -> str:
    """Convert an HTML document to readable plain text (stdlib only)."""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Truncated/garbage markup still yields whatever was parsed so far
        pass
    return parser.get_text()


def fetch_urllib(url: str, timeout: int = 30) -> Tuple[str, Optional[str]]:
    """Fetch a URL with urllib. Returns (body_text, error_message)."""
    import urllib.request

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = None
            try:
                charset = response.headers.get_content_charset()
            except Exception:
                charset = None

            declared = response.headers.get("Content-Length")
            if declared:
                try:
                    if int(declared) > MAX_HTML_BYTES:
                        return "", (
                            f"Error: Response too large "
                            f"({int(declared) // (1024 * 1024)}MB). "
                            f"Max: {MAX_HTML_BYTES // (1024 * 1024)}MB"
                        )
                except ValueError:
                    pass

            chunks = []
            total = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_HTML_BYTES:
                    return "", (
                        f"Error: Response too large "
                        f"(> {MAX_HTML_BYTES // (1024 * 1024)}MB)"
                    )
            data = b"".join(chunks)
    except Exception as e:
        return "", f"Error fetching URL: {e}"

    for encoding in (charset, "utf-8", "latin-1"):
        if not encoding:
            continue
        try:
            return data.decode(encoding), None
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace"), None


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
        native path. Empty stdout is treated as failure so a native retry
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

    # Optional per-project URL allowlist (WEB_SEARCH_URL_ALLOW). Parsed once per
    # distinct env value so a stale compile can never outlive the env var.
    _allow_cache: Dict[str, Any] = {"raw": None, "patterns": []}

    def _url_allowlist() -> Tuple[bool, list]:
        """(configured, compiled patterns) parsed from WEB_SEARCH_URL_ALLOW"""
        raw = os.environ.get("WEB_SEARCH_URL_ALLOW", "").strip()
        if _allow_cache["raw"] == raw:
            return bool(raw), _allow_cache["patterns"]
        patterns = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                patterns.append(re.compile(line))
            except re.error as e:
                LogUtils.print(f"  [!] WEB_SEARCH_URL_ALLOW: invalid regex {line!r}: {e}")
        _allow_cache["raw"] = raw
        _allow_cache["patterns"] = patterns
        return bool(raw), patterns

    def check_url_allowed(url: str):
        """None when the fetch is allowed, else the refusal message"""
        configured, patterns = _url_allowlist()
        if not configured:
            return None
        if not patterns:
            return (
                f"URL refused: WEB_SEARCH_URL_ALLOW is set but contains no valid regex "
                f"(all patterns failed to compile) - refusing every fetch.\nURL: {url}"
            )
        if any(p.search(url) for p in patterns):
            return None
        listed = "\n".join(f"  - {p.pattern}" for p in patterns)
        return (
            f"URL refused by project allowlist (WEB_SEARCH_URL_ALLOW): {url}\n"
            f"No pattern matches this URL. Allowed patterns:\n{listed}"
        )

    def _on_before_approval_prompt(tool_name: str, arguments: Dict[str, Any]):
        """Skip the approval prompt for URLs the allowlist forbids.

        Returning the refusal text (not just False) means the model gets the
        pattern list as the tool result instead of a generic "cancelled by
        user", and the user is never asked about a fetch that cannot happen.
        Allowed URLs and the unset-allowlist case return None: normal prompt.
        """
        if tool_name != "get_url_content" or not _url_allowlist()[0]:
            return None
        url = (arguments or {}).get("url", "").strip()
        if not url:
            return None
        return check_url_allowed(url)

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
        """Fetch URL as readable text: lynx when usable, else stdlib HTML->text."""
        import subprocess

        content = None

        if shutil.which("lynx"):
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
                    text = result.stdout.decode("utf-8", errors="replace")
                except Exception:
                    text = result.stdout.decode("latin-1", errors="replace")
                if result.returncode == 0 and text.strip():
                    content = text
            except subprocess.TimeoutExpired:
                return "Error: Request timed out after 30 seconds"
            except Exception:
                # exec blocked (sandbox), binary gone, seal refusal: fall through
                content = None

        engine = "lynx"
        if content is None:
            # Pure-stdlib fallback: fetch HTML, strip it down to text
            engine = "stdlib"
            html, error = fetch_urllib(url)
            if error:
                return error
            content = html_to_text(html)
            if not content.strip():
                return "Error: Page contained no readable text"

        # Detect if provider is blocking the request
        if detect_blocking(content):
            warning = (
                "\n"
                "[!] WARNING: Search provider has blocked this request as bot traffic.\n"
                "    The AI cannot continue using web search until this is resolved.\n\n"
            )
            content = warning + content

        if engine != "lynx" and Config.debug():
            LogUtils.print(f"  - fetch_url_text: lynx unavailable, used {engine} fallback")

        return content

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
        text, error = fetch_urllib(url)
        return error if error else text

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

        # Project allowlist gate - runs before any fetcher (gateway included).
        refusal = check_url_allowed(url)
        if refusal:
            return {
                "tool": "get_url_content",
                "friendly": "Error: URL not allowed by project allowlist",
                "detailed": refusal,
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
        """Raw fetch attempt chain (gorl -> curl -> stdlib urllib)."""
        avail = [b for b in ("gorl", "curl") if shutil.which(b)]
        if not avail:
            return "stdlib urllib"
        return " -> ".join(avail) + " -> stdlib urllib"

    # Format function for get_url_content (shows URL during approval)
    def format_get_url_content(args):
        """Format arguments for get_url_content, including gateway mode"""
        url = args.get("url", "")
        page = args.get("page", 1)
        raw = args.get("raw", False)
        raw_str = " (raw HTML)" if raw else " (text)"
        if raw:
            mode = f"native raw HTML ({_raw_fetcher_label()}), no gateway"
        elif _search_script_path():
            mode = "gateway (WEB_SEARCH_SCRIPT)"
        else:
            mode = "native lynx" if shutil.which("lynx") else "native stdlib (urllib -> text)"
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
        description=(
            "Fetch URL content as readable text (lynx -dump, or a pure-stdlib "
            "HTML->text fallback when lynx cannot run). Set raw=true for raw HTML."
        ),
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
                    "description": "Fetch raw HTML instead of readable text (default: false)",
                    "default": False
                }
            },
            "required": ["url"]
        },
        auto_approved=False,
        format_arguments=format_get_url_content
    )

    # Denied URLs never reach the prompt; the hook returns the refusal text.
    ctx.register_hook("before_approval_prompt", _on_before_approval_prompt)

    if Config.debug():
        LogUtils.print("  - web_search tool (auto-approved)")
        LogUtils.print("  - get_url_content tool")
