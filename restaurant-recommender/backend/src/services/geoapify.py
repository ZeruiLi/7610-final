from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import Configuration
from models import GeocodeResult, Place


class GeoapifyError(RuntimeError):
    pass


@dataclass
class _RetryPolicy:
    retries: int = 3
    base_delay: float = 0.5


class GeoapifyClient:
    def __init__(self, cfg: Configuration) -> None:
        self.cfg = cfg
        self.base = cfg.geoapify_base_url.rstrip("/")
        self.session = requests.Session()
        self._cache_ttl = 60 * 30  # 30 minutes
        self._cache_max = 128
        self._geocode_cache: OrderedDict[str, Tuple[float, Optional[GeocodeResult]]] = OrderedDict()
        self._places_cache: OrderedDict[str, Tuple[float, List[Place]]] = OrderedDict()

    def _cache_get(self, cache: OrderedDict[str, Tuple[float, Any]], key: str):  # type: ignore[valid-type]
        entry = cache.get(key)
        if not entry:
            return None
        ts, value = entry
        if time.time() - ts > self._cache_ttl:
            cache.pop(key, None)
            return None
        cache.move_to_end(key)
        return value

    def _cache_set(self, cache: OrderedDict[str, Tuple[float, Any]], key: str, value):  # type: ignore[valid-type]
        if len(cache) >= self._cache_max:
            cache.popitem(last=False)
        cache[key] = (time.time(), value)

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base}{path}"
        headers = {"Accept": "application/json"}
        params = {**params, "apiKey": self.cfg.geoapify_api_key}
        policy = _RetryPolicy()
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.get(url, headers=headers, params=params, timeout=self.cfg.geoapify_timeout)
            except requests.RequestException as exc:  # network error
                if attempt <= policy.retries:
                    time.sleep(policy.base_delay * attempt)
                    continue
                raise GeoapifyError(f"request error: {exc}")

            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt <= policy.retries:
                    time.sleep(policy.base_delay * attempt)
                    continue
                snippet = resp.text[:300]
                raise GeoapifyError(f"upstream {resp.status_code}: {snippet}")

            if not resp.ok:
                snippet = resp.text[:300]
                raise GeoapifyError(f"upstream {resp.status_code}: {snippet}")

            try:
                return resp.json()
            except ValueError:
                raise GeoapifyError("invalid json response")

    def geocode(self, text: str, *, lang: str = "zh") -> Optional[GeocodeResult]:
        key = f"geocode:{lang}:{text.strip().lower()}"
        cached = self._cache_get(self._geocode_cache, key)
        if cached is not None:
            return cached
        payload = self._get(
            "/v1/geocode/search",
            {"text": text, "limit": 1, "lang": lang},
        )
        features = payload.get("features") or []
        if not features:
            return None
        props = (features[0].get("properties") or {})
        lon = props.get("lon")
        lat = props.get("lat")
        bbox = props.get("bbox")
        bbox_tuple = None
        if isinstance(bbox, list) and len(bbox) == 4:
            # Geoapify bbox order is [min_lon, min_lat, max_lon, max_lat]
            bbox_tuple = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        if lon is None or lat is None:
            self._cache_set(self._geocode_cache, key, None)
            return None
        result = GeocodeResult(lon=float(lon), lat=float(lat), bbox=bbox_tuple)
        self._cache_set(self._geocode_cache, key, result)
        return result

    def _parse_places(self, features: List[dict]) -> List[Place]:
        results: list[Place] = []
        for feat in features:
            props = feat.get("properties") or {}
            name = props.get("name") or props.get("street") or "Restaurant"
            address = props.get("formatted") or props.get("address_line1")
            lon = props.get("lon")
            lat = props.get("lat")
            if lon is None or lat is None:
                geom = feat.get("geometry") or {}
                coords = (geom.get("coordinates") or [None, None])
                if isinstance(coords, list) and len(coords) >= 2:
                    lon, lat = coords[0], coords[1]
            website = props.get("website") or None
            opening_hours = props.get("opening_hours") or None
            rating = props.get("rating") if isinstance(props.get("rating"), (int, float)) else None
            datasource_url = None
            datasource = (props.get("datasource") or {}).get("raw") or {}
            if isinstance(datasource, dict):
                datasource_url = datasource.get("url") or None
            tags: list[str] = []
            if props.get("categories"):
                if isinstance(props["categories"], list):
                    tags = [str(x) for x in props["categories"]]

            if lon is None or lat is None:
                continue

            if not datasource_url:
                q = urllib.parse.quote_plus(f"{name} {address or ''} {lat},{lon}")
                datasource_url = f"https://www.google.com/maps/search/?api=1&query={q}"

            results.append(
                Place(
                    name=str(name),
                    address=(str(address) if address else None),
                    lon=float(lon),
                    lat=float(lat),
                    website=(str(website) if website else None),
                    opening_hours=(str(opening_hours) if opening_hours else None),
                    datasource_url=(str(datasource_url) if datasource_url else None),
                    tags=tags,
                    rating=(float(rating) if rating is not None else None),
                )
            )
        return results

    def places_rect(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        *,
        categories: Optional[str] = None,
        limit: int = 20,
        lang: str = "zh",
    ) -> List[Place]:
        key = f"rect:{categories or '*'}:{lang}:{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}:{limit}"
        cached = self._cache_get(self._places_cache, key)
        if cached is not None:
            return list(cached)
        rect = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        center_lon = (min_lon + max_lon) / 2.0
        center_lat = (min_lat + max_lat) / 2.0
        params = {
            "filter": f"rect:{rect}",
            "limit": limit,
            "bias": f"proximity:{center_lon},{center_lat}",
            "lang": lang,
        }
        if categories:
            params["categories"] = categories
        payload = self._get("/v2/places", params)
        features = payload.get("features") or []
        results = self._parse_places(features)
        self._cache_set(self._places_cache, key, list(results))
        return results

    def places_circle(
        self,
        lon: float,
        lat: float,
        *,
        radius_km: float,
        categories: Optional[str] = None,
        limit: int = 20,
        lang: str = "en",
    ) -> List[Place]:
        radius_m = max(radius_km, 0.1) * 1000.0
        key = f"circle:{categories or '*'}:{lang}:{lon:.4f},{lat:.4f}:{radius_m:.0f}:{limit}"
        cached = self._cache_get(self._places_cache, key)
        if cached is not None:
            return list(cached)
        params = {
            "filter": f"circle:{lon},{lat},{radius_m:.0f}",
            "bias": f"proximity:{lon},{lat}",
            "limit": limit,
            "lang": lang,
        }
        if categories:
            params["categories"] = categories
        payload = self._get("/v2/places", params)
        features = payload.get("features") or []
        results = self._parse_places(features)
        self._cache_set(self._places_cache, key, list(results))
        return results
