import re
import json
import urllib.request
import urllib.parse
import subprocess
from typing import Dict, Any, List, Optional
from tools.web import DEFAULT_HTTP_HEADERS

def browse_web_headless(url: str, extract_links: bool = True) -> Dict[str, Any]:
    """
    Headless Web Automation tool.
    Fetches web page HTML, cleans noise, extracts core text, headings, and interactive links.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    headers = DEFAULT_HTTP_HEADERS

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            html = response.read().decode("utf-8", errors="ignore")
            final_url = response.geturl()

        # Extract title
        title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_m.group(1).strip() if title_m else "No Title"

        # Remove scripts, styles, and SVG noise
        clean_html = re.sub(r'<(script|style|svg|path)[^>]*>.*?</\1>', '', html, flags=re.IGNORECASE | re.DOTALL)

        # Extract links if requested
        links: List[Dict[str, str]] = []
        if extract_links:
            for match in re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', clean_html, re.IGNORECASE | re.DOTALL):
                link_url = match.group(1).strip()
                link_text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                if link_text and not link_url.startswith("javascript:") and not link_url.startswith("#"):
                    full_link = urllib.parse.urljoin(final_url, link_url)
                    links.append({"text": link_text[:60], "url": full_link})
                if len(links) >= 15:
                    break

        # Extract readable body text
        body_text = re.sub(r'<[^>]+>', ' ', clean_html)
        body_text = re.sub(r'\s+', ' ', body_text).strip()

        return {
            "success": True,
            "url": final_url,
            "title": title,
            "content_preview": body_text[:2500],
            "links": links[:10],
            "word_count": len(body_text.split())
        }

    except Exception as e:
        return {"success": False, "url": url, "error": f"Web Automation Error: {str(e)}"}


def automate_browser(url: str, actions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Advanced Browser Automation Engine.
    Supports script execution, link clicking, form interaction, and rendering content.
    Attempts Playwright automation if installed; gracefully falls back to urllib engine.
    """
    # Check if Playwright is available
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=15000)

            # Perform requested interaction actions
            if actions:
                for act in actions:
                    act_type = act.get("type")
                    if act_type == "click":
                        selector = act.get("selector")
                        if selector:
                            page.click(selector, timeout=5000)
                    elif act_type == "fill":
                        selector = act.get("selector")
                        val = act.get("value", "")
                        if selector:
                            page.fill(selector, val, timeout=5000)
                    elif act_type == "press":
                        key = act.get("key", "Enter")
                        page.keyboard.press(key)

            title = page.title()
            content = page.inner_text("body")
            final_url = page.url
            browser.close()

            return {
                "success": True,
                "engine": "playwright",
                "url": final_url,
                "title": title,
                "content_preview": content[:2500],
                "word_count": len(content.split())
            }
    except Exception:
        # Fallback to standard headless web engine
        res = browse_web_headless(url)
        res["engine"] = "urllib_fallback"
        return res
