import requests
import json
import re
import urllib.parse
from typing import Dict, Any, List

DEFAULT_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

HEADERS = {"User-Agent": DEFAULT_HTTP_HEADERS["User-Agent"]}

def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Performs a reliable web & encyclopedia search using DuckDuckGo Instant API & Wikipedia OpenSearch.
    """
    results: List[Dict[str, str]] = []

    # 1. Try DuckDuckGo Instant Answer API
    try:
        ddg_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote_plus(query)}&format=json"
        res = requests.get(ddg_url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get("AbstractText"):
                results.append({
                    "url": data.get("AbstractURL", "https://duckduckgo.com"),
                    "snippet": data.get("AbstractText")
                })
            for topic in data.get("RelatedTopics", []):
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "url": topic.get("FirstURL", "https://duckduckgo.com"),
                        "snippet": topic.get("Text")
                    })
                if len(results) >= max_results:
                    break
    except Exception:
        pass

    # 2. If results are sparse, fallback to Wikipedia OpenSearch API
    if len(results) < max_results:
        try:
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote_plus(query)}&limit={max_results}&namespace=0&format=json"
            res = requests.get(wiki_url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if len(data) >= 4:
                    titles = data[1]
                    snippets = data[2]
                    urls = data[3]
                    for title, snip, u in zip(titles, snippets, urls):
                        if snip and snip not in [r["snippet"] for r in results]:
                            results.append({
                                "url": u,
                                "snippet": f"[{title}] {snip}"
                            })
        except Exception:
            pass

    if not results:
        results.append({
            "url": f"https://duckduckgo.com/?q={urllib.parse.quote_plus(query)}",
            "snippet": f"Search completed for '{query}'. Direct summary unavailable; use fetch_url on specific targets."
        })

    return {
        "success": True,
        "query": query,
        "results": results[:max_results]
    }


def fetch_url(url: str, max_chars: int = 4000) -> Dict[str, Any]:
    """
    Fetches text content from a web URL and extracts clean readable text.
    """
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return {"success": False, "content": "", "error": f"HTTP error {res.status_code}"}

        html = res.text
        text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        truncated = text[:max_chars]
        if len(text) > max_chars:
            truncated += f"\n... [Content truncated at {max_chars} chars]"

        return {
            "success": True,
            "url": url,
            "content": truncated
        }
    except Exception as e:
        return {"success": False, "content": "", "error": str(e)}
