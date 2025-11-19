from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from hello_agents.tools import SearchTool

from models import Place


@dataclass
class DetailContext:
    sources: List[Dict[str, str]]
    raw_text: str
    extracted: Dict[str, Any]
    trust_score: float = 0.0
    hits: int = 0


_DETAIL_CACHE: dict[str, Tuple[float, DetailContext]] = {}
_CACHE_TTL_SEC = 60 * 60  # 1h
_SEARCH = SearchTool(backend="advanced")


def _cache_key(place: Place, lang: str) -> str:
    return f"{lang}|{place.name}|{place.address}|{place.lat:.5f},{place.lon:.5f}"


def _dedupe_sources(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for it in items:
        url = (it.get("url") or "").strip()
        title = (it.get("title") or url).strip()
        weight = float(it.get("weight") or 0.0)
        key = (title.lower(), url.lower())
        existing = seen.get(key)
        if not existing or weight > float(existing.get("weight", 0.0)):
            seen[key] = {"title": title, "url": url, "weight": round(weight, 3)}
    return list(seen.values())[:5]


def _source_weight(url: str, place: Place) -> float:
    from urllib.parse import urlparse

    disallowed = (
        "zhipin.com",
        "linkedin.com",
        "glassdoor.com",
        "indeed.com",
        "bosszhipin",
        "lagou.com",
    )
    if any(bad in url for bad in disallowed):
        return 0.0

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "yelp.com" in host:
        return 1.0
    if "tripadvisor" in host:
        return 0.9
    if "opentable" in host or "resy" in host:
        return 0.85
    if "google.com" in host and "maps" in parsed.path:
        return 0.8
    if any(keyword in host for keyword in ("ubereats", "doordash", "grubhub")):
        return 0.4
    name_tokens = [token for token in place.name.lower().split() if len(token) > 3]
    if name_tokens and all(token in host for token in name_tokens[:2]):
        return 0.9
    return 0.5


_RATING_PATTERN = re.compile(r"(\d(?:\.\d)?)\s*(?:/\s*5|star)", re.I)


def _extract_rating(snippet: str) -> Optional[str]:
    match = _RATING_PATTERN.search(snippet)
    if not match:
        return None
    value = match.group(1)
    return f"{value}/5"


def fetch_details(place: Place, lang: str = "en") -> DetailContext:
    """Fetch external details for a place using HelloAgents SearchTool.

    Returns small context with sources + concatenated snippets suitable for LLM.
    A simple 1h in-memory cache avoids repeated calls during interactive usage.
    """
    key = _cache_key(place, lang)
    now = time.time()
    cached = _DETAIL_CACHE.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    query = f"{place.name} {place.address or ''} menu signature dishes hours phone website reviews"
    try:
        payload = _SEARCH.run(
            {
                "input": query,
                "backend": "advanced",
                "mode": "structured",
                "max_results": 6,
                "fetch_full_page": False,
            }
        )
    except Exception:
        payload = {"results": []}

    items = payload.get("results", []) if isinstance(payload, dict) else []
    sources_with_weight: List[Dict[str, Any]] = []
    raw_parts: List[str] = []
    extracted: Dict[str, Any] = {"ratings": []}

    for r in items:
        url = r.get("url") or ""
        if not url:
            continue
        title = r.get("title") or url
        snippet = r.get("content") or r.get("snippet") or ""
        weight = _source_weight(url, place)
        if weight <= 0:
            continue
        sources_with_weight.append({"title": title, "url": url, "weight": weight})
        if snippet:
            raw_parts.append(f"Source: {title}\nURL: {url}\n{snippet}\n")
            rating = _extract_rating(snippet)
            if rating:
                extracted.setdefault("ratings", []).append(rating)

    deduped_sources = _dedupe_sources(sources_with_weight)
    hits = len(deduped_sources)
    trust_score = 0.0
    if hits:
        trust_score = sum(float(src.get("weight", 0.0)) for src in deduped_sources) / hits

    ctx = DetailContext(
        sources=deduped_sources,
        raw_text="\n".join(raw_parts)[:4000],
        extracted=extracted,
        trust_score=round(trust_score, 3),
        hits=hits,
    )
    _DETAIL_CACHE[key] = (now, ctx)
    return ctx


async def fetch_details_async(place: Place, lang: str = "en") -> DetailContext:
    """Async wrapper for fetch_details to allow concurrent execution."""
    import asyncio
    return await asyncio.to_thread(fetch_details, place, lang)
