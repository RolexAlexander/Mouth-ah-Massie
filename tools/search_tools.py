"""Search and fetch tools the Researcher agent uses.

We talk directly to SearXNG over HTTP and fetch full page text with
trafilatura. We deliberately do NOT use an MCP server here — these are
native ADK tools, which gives the Researcher tighter, typed control and
faster startup than `npx` subprocess MCP servers.
"""
from __future__ import annotations

import asyncio

import httpx
import trafilatura

from deep_research.config import CONFIG


async def searxng_search(query: str, max_results: int = 8) -> list[dict]:
    """Search the web via SearXNG.

    Args:
        query: The search query string.
        max_results: How many results to return (max 20).

    Returns:
        A list of dicts with 'url', 'title', 'snippet'. Empty list on failure.
    """
    max_results = min(max(1, max_results), 20)
    params = {"q": query, "format": "json", "language": "en", "safesearch": 0}
    url = f"{CONFIG.searxng_base_url.rstrip('/')}/search"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return [{"error": f"SearXNG request failed: {e}"}]

    results = data.get("results", [])[:max_results]
    return [
        {
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "snippet": item.get("content", ""),
        }
        for item in results
    ]


async def fetch_page(url: str, max_chars: int = 8000) -> dict:
    """Fetch a single web page and return cleaned text.

    Args:
        url: The page URL.
        max_chars: Truncate output to this many characters (default 8000).

    Returns:
        Dict with 'url', 'title', 'text'. Errors return 'text' with error message.
    """
    try:
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True,
            headers={"User-Agent": "DeepResearchADK/0.1 (+local research)"},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as e:
        return {"url": url, "title": "", "text": f"[fetch failed: {e}]"}

    # trafilatura is synchronous; run in executor to not block
    loop = asyncio.get_running_loop()
    extracted = await loop.run_in_executor(
        None, lambda: trafilatura.extract(html, include_comments=False, favor_recall=True) or ""
    )
    title = ""
    try:
        meta = trafilatura.extract_metadata(html)
        if meta and meta.title:
            title = meta.title
    except Exception:
        pass

    if len(extracted) > max_chars:
        extracted = extracted[:max_chars] + "\n...[truncated]"

    return {"url": url, "title": title, "text": extracted}


# Synchronous wrappers — ADK tool functions can be either, but sync is simpler
# for the LLM to reason about.
async def web_search(query: str, max_results: int = 8) -> list[dict]:
    """Run a web search via SearXNG.

    Use this to find relevant pages for a sub-question.

    Args:
        query: A focused 3-8 word query. Avoid quotes and operators.
        max_results: 1-20. Default 8.

    Returns:
        List of {'url', 'title', 'snippet'}.
    """
    return await searxng_search(query, max_results)


async def read_page(url: str) -> dict:
    """Fetch and clean a single web page for full reading.

    Use this after `web_search` when a snippet looks promising and you need
    the full content.

    Args:
        url: A URL returned by web_search.

    Returns:
        Dict with 'url', 'title', 'text' (cleaned article body, up to 8000 chars).
    """
    return await fetch_page(url)
