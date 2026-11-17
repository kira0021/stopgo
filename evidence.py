"""Public, free, key-less evidence sources.

  * GitHub repository search  -> existing free alternatives (competition)
  * Stack Overflow search     -> people asking about the problem (pain)
  * Hacker News (Algolia)     -> discussion volume (interest)

Every number carries the URL it came from. If a source is unreachable the
value is None and marked "unavailable": the system never fills in a number.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

UA = {"User-Agent": "StopGo-venture-builder (open source; hackathon prototype)"}


def _get(url: str, headers: dict | None = None, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def offline() -> bool:
    return os.getenv("EVIDENCE_OFFLINE", "0") == "1"


def github_alternatives(query: str) -> dict:
    human = f"https://github.com/search?q={urllib.parse.quote(query)}&type=repositories&s=stars&o=desc"
    if offline():
        return {"count": None, "top_stars": None, "top": [], "url": human, "status": "unavailable (offline mode)"}
    api = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page=5"
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        r = _get(api, headers)
        top = [{"name": i["full_name"], "stars": i["stargazers_count"], "url": i["html_url"],
                "description": (i.get("description") or "")[:140]} for i in r.get("items", [])]
        return {"count": r.get("total_count"), "top_stars": top[0]["stars"] if top else 0, "top": top,
                "url": human, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"count": None, "top_stars": None, "top": [], "url": human, "status": f"unavailable ({type(exc).__name__})"}


def stackoverflow_questions(query: str) -> dict:
    human = f"https://stackoverflow.com/search?q={urllib.parse.quote(query)}"
    if offline():
        return {"count": None, "url": human, "status": "unavailable (offline mode)"}
    api = ("https://api.stackexchange.com/2.3/search/advanced?site=stackoverflow&filter=total&q="
           + urllib.parse.quote(query))
    try:
        r = _get(api)
        return {"count": r.get("total"), "url": human, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"count": None, "url": human, "status": f"unavailable ({type(exc).__name__})"}


def hackernews_mentions(query: str) -> dict:
    human = f"https://hn.algolia.com/?q={urllib.parse.quote(query)}&type=story"
    if offline():
        return {"count": None, "url": human, "status": "unavailable (offline mode)"}
    api = f"https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=5&query={urllib.parse.quote(query)}"
    try:
        r = _get(api)
        top = [{"title": h.get("title"), "points": h.get("points"),
                "url": f"https://news.ycombinator.com/item?id={h.get('objectID')}"} for h in r.get("hits", [])]
        return {"count": r.get("nbHits"), "top": top, "url": human, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"count": None, "top": [], "url": human, "status": f"unavailable ({type(exc).__name__})"}


def gather(keywords: str, cache_path: str | None = None) -> dict:
    """Collect all public signals once per run (cached for reproducibility)."""
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("keywords") == keywords:
            return cached
    data = {
        "keywords": keywords,
        "github": github_alternatives(keywords),
        "stackoverflow": stackoverflow_questions(keywords),
        "hackernews": hackernews_mentions(keywords),
    }
    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    return data


def source_urls(public: dict) -> list[str]:
    urls = []
    for key in ("github", "stackoverflow", "hackernews"):
        src = public.get(key) or {}
        if src.get("status") == "ok":
            urls.append(src["url"])
            urls += [t["url"] for t in src.get("top", []) if t.get("url")]
    return urls
