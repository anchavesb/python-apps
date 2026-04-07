"""Web browsing tools: DuckDuckGo search and page fetch.

Two built-in Tool implementations that do not rely on OpenAPI auto-discovery:
  - WebSearchTool  (web_browse_search): query → JSON list of results
  - PageFetchTool  (web_browse_fetch):  URL → stripped page text
"""

from __future__ import annotations

import json
import re

import httpx
from bs4 import BeautifulSoup

from dolores_common.logging import get_logger

from .base import Tool

log = get_logger(__name__)

_DDG_URL = "https://html.duckduckgo.com/html/"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_DDG_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "en-US,en;q=0.9",
}
_FETCH_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
_MAX_RESULTS = 6
_MAX_PAGE_CHARS = 5000


class WebSearchTool(Tool):
    """Search the web via DuckDuckGo HTML and return a list of results."""

    @property
    def name(self) -> str:
        return "web_browse_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for current information. Returns a list of results "
            "with title, snippet, and URL. Use when the user asks to browse, "
            "search the web, look up, or find something online."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> str:
        query: str = kwargs.get("query", "")
        if not query:
            return "No query provided."

        log.info("web_search", query=query[:120])

        try:
            async with httpx.AsyncClient(headers=_DDG_HEADERS, follow_redirects=True, timeout=15) as client:
                resp = await client.post(_DDG_URL, data={"q": query, "b": "", "kl": "us-en"})
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            log.error("web_search_failed", query=query[:80], error=str(e))
            return f"Search failed: {e}"

        soup = BeautifulSoup(html, "html.parser")
        results = []

        for div in soup.select("div.result")[:_MAX_RESULTS]:
            title_tag = div.select_one("a.result__a")
            snippet_tag = div.select_one("a.result__snippet")
            url_tag = div.select_one("a.result__url")

            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            display_url = url_tag.get_text(strip=True) if url_tag else ""

            # DDG result hrefs are redirect links; extract the actual URL
            href = title_tag.get("href", "")
            url = _extract_uddg(href) or display_url or href
            if url and not url.startswith(("http://", "https://")):
                url = "https://" + url

            if title:
                results.append({"title": title, "snippet": snippet, "url": url})

        if not results:
            return "No results found."

        # Add a text summary to help the LLM
        summary_lines = [f"- {r['title']}: {r['snippet']} ({r['url']})" for r in results]
        text_summary = "I found these results on the web:\n" + "\n".join(summary_lines)

        final_data = {"results": results, "text": text_summary}

        log.info("web_search_done", query=query[:80], count=len(results))
        return json.dumps(final_data, ensure_ascii=False)


_UDDG_RE = re.compile(r"uddg=([^&]+)")


def _extract_uddg(href: str) -> str:
    """Pull the real URL out of a DuckDuckGo redirect href."""
    m = _UDDG_RE.search(href)
    if m:
        from urllib.parse import unquote

        return unquote(m.group(1))
    return ""


class PageFetchTool(Tool):
    """Fetch a web page and return its readable text content."""

    @property
    def name(self) -> str:
        return "web_browse_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch the full text content of a web page at the given URL. "
            "Use when the user asks to open or show a specific URL."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL of the page to fetch.",
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs) -> str:
        url: str = kwargs.get("url", "")
        if not url:
            return "No URL provided."

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        log.info("page_fetch", url=url[:200])

        try:
            async with httpx.AsyncClient(headers=_FETCH_HEADERS, follow_redirects=True, timeout=20) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            log.error("page_fetch_failed", url=url[:120], error=str(e))
            return f"Failed to fetch page: {e}"

        soup = BeautifulSoup(html, "html.parser")

        # Remove non-content tags
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        if len(text) > _MAX_PAGE_CHARS:
            text = text[:_MAX_PAGE_CHARS] + "\n\n[content truncated]"

        log.info("page_fetch_done", url=url[:120], chars=len(text))
        return text
