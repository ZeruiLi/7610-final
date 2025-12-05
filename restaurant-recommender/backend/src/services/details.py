from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from hello_agents.tools import SearchTool
from loguru import logger

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
        snippet = it.get("snippet") or ""
        key = (title.lower(), url.lower())
        existing = seen.get(key)
        if not existing or weight > float(existing.get("weight", 0.0)):
            seen[key] = {
                "title": title, 
                "url": url, 
                "weight": round(weight, 3),
                "snippet": snippet
            }
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
        "yellowpages.com",
        "restaurantji.com",
        "sluurpy.com",
        "us-restaurant.com",
        "menuism.com",
    )
    if any(bad in url for bad in disallowed):
        return 0.0

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    
    # High authority
    if any(d in host for d in ("theinfatuation.com", "eater.com", "michelin.com", "timeout.com", "bonappetit.com")):
        return 1.2  # Bonus weight
    
    if "yelp.com" in host:
        return 1.0
    if "tripadvisor" in host:
        return 0.9
    if "opentable" in host or "resy" in host or "tock" in host:
        return 0.85
    if "google.com" in host and "maps" in parsed.path:
        return 0.8
    if any(keyword in host for keyword in ("ubereats", "doordash", "grubhub", "postmates")):
        return 0.4
        
    name_tokens = [token for token in place.name.lower().split() if len(token) > 3]
    if name_tokens and all(token in host for token in name_tokens[:2]):
        return 0.9
    return 0.5


_RATING_PATTERN = re.compile(
    r"(\d(?:\.\d+)?)\s*(?:/|of)?\s*5(?:\.0)?|\b(\d(?:\.\d+)?)\s*stars?\b",
    re.I,
)


def _extract_rating(snippet: str) -> Optional[float]:
    match = _RATING_PATTERN.search(snippet)
    if not match:
        return None
    value = match.group(1) or match.group(2)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

    # Construct a more targeted query
    # Try to extract a city/area context from address to keep query short but specific
    loc_context = place.address or ""
    if loc_context:
        # heuristic: take the last 2 parts of address (usually City, State Zip)
        parts = loc_context.split(",")
        if len(parts) > 1:
            loc_context = ",".join(parts[-2:]).strip()
    
    query = f"{place.name} {loc_context} restaurant reviews menu"
    
    try:
        # Already running in thread via fetch_details_async, so just call directly
        payload = _SEARCH.run({
            "input": query,
            "backend": "advanced",
            "mode": "structured",
            "max_results": 5,  # Reduce from 8 to 5 to speed up
            "fetch_full_page": False,
        })
    except Exception as exc:
        logger.warning("details search failed for %s: %s", query, exc)
        payload = {"results": []}

    items = payload.get("results", []) if isinstance(payload, dict) else []
    sources_with_weight: List[Dict[str, Any]] = []
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
        
        sources_with_weight.append({
            "title": title, 
            "url": url, 
            "weight": weight,
            "snippet": snippet
        })
        
        if snippet:
            rating = _extract_rating(snippet)
            if rating:
                extracted.setdefault("ratings", []).append(rating)

    backend_used = payload.get("backend") if isinstance(payload, dict) else None
    deduped_sources = _dedupe_sources(sources_with_weight)
    if backend_used:
        logger.debug("details backend=%s sources=%d", backend_used, len(deduped_sources))
    
    # Smart truncation: sort by weight desc, then concatenate
    deduped_sources.sort(key=lambda x: float(x.get("weight", 0)), reverse=True)
    
    raw_parts: List[str] = []
    current_len = 0
    MAX_LEN = 4000
    
    for src in deduped_sources:
        snippet = src.get("snippet", "")
        # Remove snippet from source dict to save space in final output list
        if "snippet" in src:
            del src["snippet"]
            
        if not snippet:
            continue
            
        part = f"Source: {src['title']}\nURL: {src['url']}\n{snippet}\n\n"
        if current_len + len(part) > MAX_LEN:
            remaining = MAX_LEN - current_len
            if remaining > 100:
                raw_parts.append(part[:remaining] + "...")
            break
        raw_parts.append(part)
        current_len += len(part)

    hits = len(deduped_sources)
    trust_score = 0.0
    if hits:
        trust_score = sum(float(src.get("weight", 0.0)) for src in deduped_sources) / hits

    ctx = DetailContext(
        sources=deduped_sources,
        raw_text="".join(raw_parts),
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
