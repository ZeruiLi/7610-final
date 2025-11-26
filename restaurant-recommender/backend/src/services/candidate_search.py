from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from config import Configuration
from models import GeocodeResult, Place, PreferenceSpec
from services.bbox_builder import expand_bbox_from_center
from services.geoapify import GeoapifyClient, GeoapifyError


US_CITY_REGISTRY: Dict[str, Dict[str, object]] = {
    "seattle": {
        "canonical": "Seattle",
        "state": "WA",
        "center": (-122.3321, 47.6062),
        "aliases": {"seattle wa", "seattle washington", "seattle, wa"},
        "areas": {
            "capitol hill": (-122.3204, 47.6230),
            "capitolhill": (-122.3204, 47.6230),
            "u district": (-122.3035, 47.6603),
            "university district": (-122.3035, 47.6603),
            "ballard": (-122.3800, 47.6686),
            "fremont": (-122.3493, 47.6512),
            "queen anne": (-122.3570, 47.6265),
            "south lake union": (-122.3381, 47.6235),
        },
    },
    "san francisco": {
        "canonical": "San Francisco",
        "state": "CA",
        "center": (-122.4194, 37.7749),
        "aliases": {"sf", "san francisco ca", "san francisco, ca"},
        "areas": {
            "soma": (-122.4006, 37.7817),
            "mission": (-122.4192, 37.7599),
            "mission district": (-122.4192, 37.7599),
            "fishermans wharf": (-122.4147, 37.8080),
            "north beach": (-122.4109, 37.8061),
            "nob hill": (-122.4156, 37.7930),
        },
    },
    "new york": {
        "canonical": "New York",
        "state": "NY",
        "center": (-73.9855, 40.7580),
        "aliases": {"nyc", "new york city", "new york, ny"},
        "areas": {
            "manhattan": (-73.9712, 40.7831),
            "midtown": (-73.9817, 40.7549),
            "flushing": (-73.8320, 40.7557),
            "brooklyn": (-73.9442, 40.6782),
            "queens": (-73.7949, 40.7282),
            "lower east side": (-73.9874, 40.7150),
        },
    },
    "los angeles": {
        "canonical": "Los Angeles",
        "state": "CA",
        "center": (-118.2437, 34.0522),
        "aliases": {"la", "los angeles ca", "los angeles, ca"},
        "areas": {
            "hollywood": (-118.3287, 34.0928),
            "santa monica": (-118.4965, 34.0195),
            "downtown": (-118.2440, 34.0407),
            "koreatown": (-118.3000, 34.0584),
            "west hollywood": (-118.3617, 34.0900),
        },
    },
    "austin": {
        "canonical": "Austin",
        "state": "TX",
        "center": (-97.7431, 30.2672),
        "aliases": {"austin tx", "austin, tx"},
        "areas": {
            "downtown": (-97.7431, 30.2687),
            "south congress": (-97.7490, 30.2490),
            "east austin": (-97.7200, 30.2639),
            "domain": (-97.7249, 30.4018),
        },
    },
}


def dedupe_places(items: List[Place]) -> List[Place]:
    seen: set[Tuple[str, int, int]] = set()
    out: list[Place] = []
    for p in items:
        key = (p.name.strip().lower(), round(p.lon, 5), round(p.lat, 5))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _normalize_token(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def _normalize_city(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = text.replace(",", " ").lower().strip()
    parts = cleaned.split()
    if parts and len(parts[-1]) == 2 and parts[-1].isalpha():
        parts = parts[:-1]
    return _normalize_token(" ".join(parts))


def _lookup_us_location(city: Optional[str], area: Optional[str]) -> Optional[Tuple[float, float]]:
    city_norm = _normalize_city(city)
    if not city_norm:
        return None

    entry = US_CITY_REGISTRY.get(city_norm)
    if not entry:
        for value in US_CITY_REGISTRY.values():
            if city_norm in value.get("aliases", set()):
                entry = value
                break
    if not entry:
        return None

    center_lon, center_lat = entry["center"]  # type: ignore[index]
    if area:
        area_norm = _normalize_token(area)
        areas = entry.get("areas", {})  # type: ignore[assignment]
        if isinstance(areas, dict) and area_norm in areas:
            return areas[area_norm]
    return center_lon, center_lat


def _safe_radius_km(spec: PreferenceSpec, cfg: Configuration) -> float:
    radius = spec.distance_km or cfg.default_distance_km
    try:
        radius = float(radius)
    except (TypeError, ValueError):
        radius = cfg.default_distance_km
    return max(radius, 0.5)


HOTPOT_TOKENS = {
    "catering.hotpot",
    "hotpot",
    "hot pot",
    "shabu",
    "shabu-shabu",
    "haidilao",
    "liuyishou",
    "boiling point",
    "little sheep",
    "mala tang",
}

SPICY_TOKENS = {
    "sichuan",
    "chongqing",
    "spicy",
    "mala",
    "hot & spicy",
    "hunan",
}

SPICY_CATEGORIES = {
    "catering.restaurant.chinese",
    "catering.restaurant.thai",
    "catering.restaurant.mexican",
    "catering.restaurant.indian",
    "catering.restaurant.korean",
    "catering.restaurant.vietnamese",
    "catering.restaurant.asian",
}


def _place_text(place: Place) -> str:
    return " ".join(filter(None, [place.name, place.address or "", " ".join(place.tags)]))


def _matches_hotpot(place: Place) -> bool:
    text = _place_text(place).lower()
    for token in HOTPOT_TOKENS:
        if token in text:
            return True
    for tag in place.tags:
        if tag and any(tok in tag.lower() for tok in HOTPOT_TOKENS):
            return True
    return False


def _matches_spicy(place: Place) -> bool:
    text = _place_text(place).lower()
    if any(token in text for token in SPICY_TOKENS):
        return True
    # Check if any tag matches spicy categories
    for tag in place.tags:
        if tag in SPICY_CATEGORIES:
            return True
    return False


def _filter_by_required_cuisines(places: List[Place], required: List[str]) -> List[Place]:
    if not required:
        return places

    filtered = places
    for req in required:
        req_lower = req.lower()
        if req_lower == "hotpot":
            filtered = [p for p in filtered if _matches_hotpot(p)]
        elif req_lower in {"spicy", "sichuan", "szechuan", "chongqing"}:
            filtered = [p for p in filtered if _matches_spicy(p)]
        else:
            filtered = [p for p in filtered if req_lower in _place_text(p).lower()]
    return filtered


def _filter_by_excluded_cuisines(places: List[Place], excluded: List[str]) -> List[Place]:
    if not excluded:
        return places
    excluded_lower = {ex.lower() for ex in excluded}
    result: list[Place] = []
    for place in places:
        is_spicy = _matches_spicy(place)
        if "spicy" in excluded_lower and is_spicy:
            continue
        result.append(place)
    return result


def _parse_minutes(value: str) -> Optional[int]:
    try:
        hour, minute = value.split(":")
        return int(hour) * 60 + int(minute)
    except (ValueError, AttributeError):
        return None


DAY_ORDER = ["mo", "tu", "we", "th", "fr", "sa", "su"]


def _segment_days(segment: str) -> List[str]:
    segment = segment.lower()
    days: set[str] = set()
    if "daily" in segment or "every day" in segment:
        return DAY_ORDER.copy()
    matches = re.findall(r"(mo|tu|we|th|fr|sa|su)(?:\s*-\s*(mo|tu|we|th|fr|sa|su))?", segment)
    if matches:
        for start, end in matches:
            if end:
                start_idx = DAY_ORDER.index(start)
                end_idx = DAY_ORDER.index(end)
                if start_idx <= end_idx:
                    days.update(DAY_ORDER[start_idx : end_idx + 1])
                else:
                    days.update(DAY_ORDER[start_idx:])
                    days.update(DAY_ORDER[: end_idx + 1])
            else:
                days.add(start)
    return list(days)


def _segment_time_range(segment: str) -> Optional[Tuple[int, int]]:
    match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", segment)
    if not match:
        return None
    open_min = _parse_minutes(match.group(1))
    close_min = _parse_minutes(match.group(2))
    if open_min is None or close_min is None:
        return None
    if close_min <= open_min:
        close_min += 24 * 60
    return open_min, close_min


def _is_open_during(place: Place, target_day: Optional[str], start_min: int, duration: int) -> Optional[bool]:
    hours = place.opening_hours
    if not hours:
        return None
    segments = [seg.strip() for seg in hours.split(";") if seg.strip()]
    if not segments:
        return None

    target_day = (target_day or "").lower()
    start = start_min
    end = start_min + duration

    evaluated = False
    for seg in segments:
        time_range = _segment_time_range(seg)
        if not time_range:
            continue
        open_min, close_min = time_range
        days = _segment_days(seg)
        if days:
            if target_day and target_day not in days:
                continue
        elif target_day:
            # no specific day info; assume applies all days
            pass

        evaluated = True
        if start >= open_min and end <= close_min:
            return True

    if evaluated:
        return False
    return None


def _apply_opening_filter(
    places: List[Place],
    spec: PreferenceSpec,
    target_day: Optional[str],
    start_min: Optional[int],
    *,
    duration_override: Optional[int] = None,
) -> List[Place]:
    if not start_min:
        return places

    filtered: list[Place] = []
    duration = duration_override if duration_override is not None else spec.min_duration_min
    for place in places:
        violations = getattr(place, "_violations", [])
        if not isinstance(violations, list):
            violations = []
        status = _is_open_during(place, target_day, start_min, duration)
        setattr(place, "_open_status", status)
        if status is True:
            setattr(place, "_violations", violations)
            filtered.append(place)
        elif status is None and not spec.strict_open_check:
            violations.append("opening_hours_unknown")
            setattr(place, "_violations", violations)
            filtered.append(place)
        else:
            # status False or None with strict => drop
            continue
    return filtered


def _parse_spec_time(spec: PreferenceSpec) -> Tuple[Optional[str], Optional[int]]:
    time_str = None
    if spec.dining_time:
        parts = spec.dining_time.split()
        if len(parts) == 2 and parts[0][:3].isalpha():
            day = parts[0].lower()[:2]
            time_str = parts[1]
            return day, _parse_minutes(time_str)
        time_str = spec.dining_time
    elif spec.datetime:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(spec.datetime)
            day = DAY_ORDER[dt.weekday()]
            return day, dt.hour * 60 + dt.minute
        except Exception:
            pass

    if time_str:
        return (None, _parse_minutes(time_str))
    return (None, None)


MAX_RADIUS_KM = 20.0


def resolve_anchor(cfg: Configuration, spec: PreferenceSpec) -> Tuple[float, float, str, str]:
    """Resolve the search anchor (lat, lon) from the preference spec."""
    client = GeoapifyClient(cfg)
    lang = spec.lang or cfg.lang_default or "en"

    preferred_point = _lookup_us_location(spec.city, spec.area) if spec.city else None
    geocode_text = spec.city or ""
    if spec.area and spec.area not in geocode_text:
        geocode_text = f"{spec.city} {spec.area}" if spec.city else spec.area

    center_lon: Optional[float] = None
    center_lat: Optional[float] = None
    anchor_type: Optional[str] = None
    anchor_label: Optional[str] = None

    def _set_center_from_geo(result: GeocodeResult | None, a_type: str, label: str) -> bool:
        nonlocal center_lon, center_lat, anchor_type, anchor_label
        if not result:
            return False
        center_lon = result.lon
        center_lat = result.lat
        anchor_type = a_type
        anchor_label = label
        return True

    def _set_center_from_coord(lat: Optional[float], lon: Optional[float]) -> bool:
        nonlocal center_lon, center_lat, anchor_type, anchor_label
        if lat is None or lon is None:
            return False
        try:
            center_lon = float(lon)
            center_lat = float(lat)
        except (TypeError, ValueError):
            return False
        anchor_type = "coord"
        anchor_label = f"{center_lat:.4f},{center_lon:.4f}"
        return True

    # 1) Explicit coordinates from client
    _set_center_from_coord(spec.anchor_lat, spec.anchor_lon)

    # 2) POI anchor
    if spec.anchor_poi and center_lon is None:
        poi_query = spec.anchor_poi
        if spec.city and spec.city.lower() not in poi_query.lower():
            poi_query = f"{spec.anchor_poi} {spec.city}"
        try:
            if _set_center_from_geo(client.geocode(poi_query, lang=lang), "poi", spec.anchor_poi):
                spec.anchor_poi = spec.anchor_poi
        except GeoapifyError:
            pass

    # 3) ZIP anchor
    if center_lon is None and spec.anchor_zip:
        try:
            if _set_center_from_geo(client.geocode(spec.anchor_zip, lang=lang), "zip", spec.anchor_zip):
                pass
        except GeoapifyError:
            pass

    # 4) Known area/city registry
    if center_lon is None and preferred_point:
        center_lon, center_lat = preferred_point
        anchor_type = "area" if spec.area else "city"
        anchor_label = spec.area or spec.city or ""

    # 5) Fallback geocode
    geo: GeocodeResult | None = None
    if center_lon is None and geocode_text:
        try:
            geo = client.geocode(geocode_text, lang=lang)
        except GeoapifyError:
            geo = None
        if not geo and spec.city:
            try:
                geo = client.geocode(spec.city, lang=lang)
            except GeoapifyError:
                geo = None
        if geo:
            _set_center_from_geo(geo, "city", geocode_text or spec.city or "")

    # 6) Sanity fallback
    if center_lon is None or center_lat is None:
        raise ValueError("Failed to determine search anchor.")

    return center_lon, center_lat, anchor_type or "city", anchor_label or ""


def search_candidates(
    cfg: Configuration, 
    spec: PreferenceSpec, 
    min_results: int = 5,
    anchor: Optional[Tuple[float, float, str, str]] = None
) -> tuple[List[Place], tuple[float, float, float, float]]:
    client = GeoapifyClient(cfg)
    lang = spec.lang or cfg.lang_default or "en"

    base_radius = _safe_radius_km(spec, cfg)
    min_results = max(1, min_results)

    required_cuisines = [c.lower() for c in (spec.must_include_cuisines or [])]
    requires_pizza = any("pizza" in cuisine for cuisine in required_cuisines)
    requires_sichuan = any(cuisine in {"sichuan", "szechuan", "spicy"} for cuisine in required_cuisines)
    
    # Define spicy-cuisine categories for targeted search
    spicy_categories = ",".join([
        "catering.restaurant.chinese",
        "catering.restaurant.thai",
        "catering.restaurant.mexican",
        "catering.restaurant.indian",
        "catering.restaurant.korean",
        "catering.restaurant.vietnamese",
        "catering.restaurant.asian",
    ])
    
    category_attempts: list[tuple[Optional[str], Optional[str], bool]]
    if requires_pizza:
        category_attempts = [
            ("catering.pizza", None, True),
            ("catering.italian", "category_relaxed:pizza->italian", False),
            ("catering.restaurant", "category_relaxed:pizza->restaurant", False),
        ]
    elif requires_sichuan:
        # Multi-stage search for Sichuan/spicy: specific cuisines first, then general
        category_attempts = [
            (spicy_categories, None, False),  # Try spicy cuisines without strict enforcement first
            ("catering.restaurant", "category_relaxed:sichuan->restaurant", False),
        ]
    else:
        category_attempts = [("catering.restaurant", None, True)]

    if anchor:
        center_lon, center_lat, anchor_type, anchor_label = anchor
    else:
        center_lon, center_lat, anchor_type, anchor_label = resolve_anchor(cfg, spec)

    spec.anchor_type = anchor_type
    spec.anchor_label = anchor_label
    default_bbox = expand_bbox_from_center(center_lon, center_lat, base_radius + cfg.bbox_padding_km)

    radius = base_radius
    final_bbox: tuple[float, float, float, float] = default_bbox
    relaxed_capture: Optional[tuple[list[Place], tuple[float, float, float, float], float]] = None
    collected: list[Place] = []
    seen: set[Tuple[str, int, int]] = set()

    while radius <= MAX_RADIUS_KM + 1e-6:
        effective_radius = radius + cfg.bbox_padding_km
        final_bbox = expand_bbox_from_center(center_lon, center_lat, effective_radius)

        for categories, category_violation, enforce_required in category_attempts:
            try:
                places = client.places_circle(
                    center_lon,
                    center_lat,
                    radius_km=effective_radius,
                    categories=categories,
                    limit=60,  # Increased to ensure enough candidates
                    lang=lang,
                )
            except GeoapifyError:
                places = []

            if not places:
                try:
                    places = client.places_rect(
                        final_bbox[0],
                        final_bbox[1],
                        final_bbox[2],
                        final_bbox[3],
                        categories=categories,
                        limit=50,  # Increased from default to support top-24 recommendations
                        lang=lang,
                    )
                except GeoapifyError:
                    places = []

            if not places:
                continue

            places = dedupe_places(places)
            for place in places:
                setattr(place, "_violations", [])

            working_places = list(places)

            if spec.must_include_cuisines and enforce_required:
                working_places = _filter_by_required_cuisines(working_places, spec.must_include_cuisines)
            if spec.must_exclude_cuisines:
                working_places = _filter_by_excluded_cuisines(working_places, spec.must_exclude_cuisines)

            target_day, start_minutes = _parse_spec_time(spec)
            working_places_after_open = _apply_opening_filter(working_places, spec, target_day, start_minutes)
            if not working_places_after_open and spec.must_include_cuisines and enforce_required:
                relaxed = list(working_places)
                for place in relaxed:
                    violations = getattr(place, "_violations", [])
                    if not isinstance(violations, list):
                        violations = []
                    violations.append("missing_required_cuisine")
                    setattr(place, "_violations", violations)
                if spec.must_exclude_cuisines:
                    relaxed = _filter_by_excluded_cuisines(relaxed, spec.must_exclude_cuisines)
                working_places_after_open = _apply_opening_filter(relaxed, spec, target_day, start_minutes)

            all_open_unknown = all(getattr(place, "_open_status", None) is None for place in working_places)

            if (
                not working_places_after_open
                and spec.strict_open_check
                and start_minutes is not None
                and all_open_unknown
            ):
                relaxed_start = max(start_minutes - 15, 20 * 60)
                relaxed_duration = max(45, spec.min_duration_min - 15)
                working_places_after_open = _apply_opening_filter(
                    working_places,
                    spec,
                    target_day,
                    relaxed_start,
                    duration_override=relaxed_duration,
                )
                if working_places_after_open:
                    for place in working_places_after_open:
                        violations = getattr(place, "_violations", [])
                        if isinstance(violations, list):
                            violations.append("opening_relaxed")
                            setattr(place, "_violations", violations)

            working_places = working_places_after_open

            # Tag strict vs. relaxed matches for ranking, but don't re-filter
            if spec.must_include_cuisines and working_places:
                strict_matches = _filter_by_required_cuisines(working_places, spec.must_include_cuisines)
                strict_ids = {id(p) for p in strict_matches}
                for place in working_places:
                    if id(place) not in strict_ids:
                        violations = getattr(place, "_violations", [])
                        if not isinstance(violations, list):
                            violations = []
                        if "missing_required_cuisine" not in violations:
                            violations.append("missing_required_cuisine")
                        setattr(place, "_violations", violations)

            if working_places:
                if radius > base_radius:
                    for place in working_places:
                        violations = getattr(place, "_violations", [])
                        if isinstance(violations, list):
                            violations.append("radius_expanded")
                            setattr(place, "_violations", violations)
                if category_violation:
                    for place in working_places:
                        violations = getattr(place, "_violations", [])
                        if isinstance(violations, list):
                            violations.append(category_violation)
                            setattr(place, "_violations", violations)

                if category_violation and requires_pizza and not enforce_required:
                    if relaxed_capture is None:
                        relaxed_capture = ([p for p in working_places], final_bbox, radius)
                    continue

                for place in working_places:
                    key = (place.name.strip().lower(), round(place.lon, 5), round(place.lat, 5))
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(place)

                if len(collected) >= min_results:
                    spec.distance_km = radius
                    return collected[:min_results], final_bbox

        if radius >= MAX_RADIUS_KM:
            break
        radius = min(MAX_RADIUS_KM, radius + max(2.0, radius * 0.5))

    if collected:
        spec.distance_km = radius
        return collected, final_bbox

    if relaxed_capture:
        places_relaxed, bbox_relaxed, radius_relaxed = relaxed_capture
        spec.distance_km = radius_relaxed
        return places_relaxed, bbox_relaxed

    return [], final_bbox
