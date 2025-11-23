from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

from models import Candidate, Place, PreferenceSpec
from utils import haversine_km


KM_TO_MILES = 0.621371

CUISINE_PATTERNS: Dict[str, Dict[str, Iterable[str]]] = {
    "Sichuan": {
        "keywords": ["sichuan", "szechuan", "spicy", "mala", "chongqing"], 
        "tags": ["catering.sichuan", "catering.restaurant.chinese", "catering.restaurant.asian"]
    },
    "Hotpot": {"keywords": ["hotpot", "hot pot"], "tags": ["catering.hotpot"]},
    "Japanese": {
        "keywords": ["japanese", "sushi", "ramen"], 
        "tags": ["catering.japanese", "catering.restaurant.japanese"]
    },
    "Korean": {
        "keywords": ["korean", "bbq", "soondubu"], 
        "tags": ["catering.korean", "catering.restaurant.korean"]
    },
    "Thai": {
        "keywords": ["thai"], 
        "tags": ["catering.thai", "catering.restaurant.thai"]
    },
    "Italian": {
        "keywords": ["italian", "pasta", "pizza"], 
        "tags": ["catering.italian", "catering.restaurant.italian"]
    },
    "Pizza": {
        "keywords": ["pizza", "pizzeria", "slice"], 
        "tags": ["catering.pizza", "catering.restaurant.pizza"]
    },
    "Mexican": {
        "keywords": ["mexican", "taco", "taqueria"], 
        "tags": ["catering.mexican", "catering.restaurant.mexican"]
    },
    "Vegan": {"keywords": ["vegan", "plant-based"], "tags": ["catering.vegan"]},
    "Seafood": {
        "keywords": ["seafood", "oyster", "lobster", "crab"], 
        "tags": ["catering.seafood"]
    },
    "BBQ": {"keywords": ["bbq", "barbecue"], "tags": ["catering.bbq"]},
}

AMBIENCE_PATTERNS: Dict[str, Iterable[str]] = {
    "quiet": ["quiet", "calm", "relaxing"],
    "family": ["family", "kid-friendly", "family friendly"],
    "casual": ["casual", "laid-back"],
    "romantic": ["romantic", "date night"],
}


def _tokenize_tags(tags: List[str]) -> Set[str]:
    tokens: set[str] = set()
    for raw in tags:
        lower = raw.lower()
        tokens.add(lower)
        tokens.update(filter(None, lower.split(".")))
    return tokens


def _match_cuisines(name_addr: str, tokens: Set[str]) -> List[str]:
    matches: list[str] = []
    for label, spec in CUISINE_PATTERNS.items():
        keywords = spec.get("keywords", [])
        tag_tokens = spec.get("tags", [])
        if any(kw in name_addr for kw in keywords) or any(tkn in tokens for tkn in tag_tokens):
            matches.append(label)
    return matches


def _match_ambience(name_addr: str) -> List[str]:
    hits: list[str] = []
    for label, kw_list in AMBIENCE_PATTERNS.items():
        if any(kw in name_addr for kw in kw_list):
            hits.append(label)
    return hits


def _score_rating(rating: Optional[float]) -> float:
    if rating is None:
        return 0.4
    return min(max(rating / 5.0, 0.0), 1.0)


def _intersects(preferences: Iterable[str], labels: Iterable[str]) -> bool:
    pref_norm = {p.strip().lower() for p in preferences if p}
    label_norm = {l.strip().lower() for l in labels if l}
    return bool(pref_norm & label_norm)


def rank_candidates(
    spec: PreferenceSpec,
    places: List[Place],
    *,
    bbox_center: Tuple[float, float],  # lon, lat
    max_results: int = 24,
) -> List[Candidate]:
    qualified: list[Candidate] = []
    fallback: list[Candidate] = []

    max_results = max(1, max_results)

    pref_cuisines = [c.lower() for c in (spec.cuisines or [])]
    pref_cuisines.extend(c.lower() for c in (spec.must_include_cuisines or []))
    pref_cuisines = list(dict.fromkeys(pref_cuisines))
    pref_ambience = [a.lower() for a in (spec.ambiance or [])]
    radius_km = max(spec.distance_km or 1.0, 0.5)

    for place in places:
        name_addr = " ".join(filter(None, [place.name, place.address, " ".join(place.tags)]))
        name_addr_lower = name_addr.lower()
        tag_tokens = _tokenize_tags(place.tags)

        cuisine_matches = _match_cuisines(name_addr_lower, tag_tokens)
        ambience_matches = _match_ambience(name_addr_lower)

        dist_km = haversine_km(bbox_center[1], bbox_center[0], place.lat, place.lon)
        dist_mi = dist_km * KM_TO_MILES
        distance_score = max(0.0, 1.0 - dist_km / (radius_km if radius_km else 1.0))

        rating_score = _score_rating(place.rating)
        has_website = 1.0 if place.website else 0.0

        cuisine_score = 0.0
        if cuisine_matches:
            cuisine_score = 0.8
            if _intersects(pref_cuisines, cuisine_matches):
                cuisine_score = 1.0
        elif pref_cuisines:
            cuisine_score = 0.2
        else:
            cuisine_score = 0.5

        ambience_score = 0.5
        if pref_ambience:
            ambience_score = 1.0 if _intersects(pref_ambience, ambience_matches) else 0.3
        elif ambience_matches:
            ambience_score = 0.7

        reliability = (rating_score * 0.5) + (has_website * 0.2) + (min(len(cuisine_matches), 3) / 3.0 * 0.3)

        # Check violations and apply penalties
        violations = getattr(place, "_violations", [])
        if not isinstance(violations, list):
            violations = []
        
        violation_penalty = 0.0
        if "missing_required_cuisine" in violations:
            violation_penalty += 0.3  # Significant penalty for not matching required cuisine
        if "category_relaxed" in str(violations):
            violation_penalty += 0.1  # Additional penalty for category relaxation
        
        total_score = (
            cuisine_score * 0.35
            + distance_score * 0.25
            + rating_score * 0.25
            + ambience_score * 0.1
            + has_website * 0.05
            - violation_penalty  # Apply penalty
        )
        debug_scores = {
            "cuisine": round(cuisine_score, 4),
            "distance": round(distance_score, 4),
            "rating": round(rating_score, 4),
            "ambience": round(ambience_score, 4),
            "website": round(has_website, 4),
        }

        pros: list[str] = []
        cons: list[str] = []
        if cuisine_matches:
            pros.append(f"Cuisine match: {', '.join(cuisine_matches)}")
        elif pref_cuisines:
            cons.append("Cuisine preference not explicitly detected")

        if ambience_matches and pref_ambience:
            pros.append(f"Ambience keywords: {', '.join(ambience_matches)}")
        elif pref_ambience:
            cons.append("Ambience preference not confirmed")

        if place.rating is not None:
            pros.append(f"Average rating {place.rating:.1f}★")
        else:
            cons.append("Rating unavailable")

        pros.append(f"Approx. {dist_mi:.1f} miles from target area")

        if spec.budget_per_capita:
            cons.append("Budget not verified against menu prices")

        reason_lines = ["- Distance: %.1f km (%.1f miles)" % (dist_km, dist_mi)]
        reason_lines.extend(f"- Pro: {text}" for text in pros)
        reason_lines.extend(f"- Risk: {text}" for text in cons)

        match_cuisine = _intersects(pref_cuisines, cuisine_matches) if pref_cuisines else bool(cuisine_matches)
        match_ambience = _intersects(pref_ambience, ambience_matches) if pref_ambience else bool(ambience_matches)

        open_status = getattr(place, "_open_status", None)
        violations = getattr(place, "_violations", [])
        if not isinstance(violations, list):
            violations = []
        if open_status is False:
            violations.append("closed_at_requested_time")
        elif open_status is None and spec.strict_open_check:
            violations.append("opening_hours_unknown")

        if spec.must_include_cuisines and not match_cuisine:
            violations.append("missing_required_cuisine")

        match_mode = "relaxed" if "missing_required_cuisine" in violations else "strict"
        
        # Assign match tier: 1=perfect match, 2=relaxed match
        match_tier = 2 if "missing_required_cuisine" in violations else 1

        candidate = Candidate(
            place=place,
            score=float(round(total_score, 4)),
            reason="\n".join(reason_lines),
            pros=pros,
            cons=cons,
            match_cuisine=match_cuisine,
            match_ambience=match_ambience,
            match_budget=bool(spec.budget_per_capita),
            match_distance=dist_km <= radius_km * 1.1,
            match_popularity=False,
            match_tier=match_tier,  # NEW: set tier
            primary_tags=cuisine_matches,
            reliability_score=float(round(reliability, 4)),
            distance_km=float(round(dist_km, 3)),
            distance_miles=float(round(dist_mi, 3)),
            source_hits=0,
            source_trust_score=0.0,
            is_open_ok=open_status is True or (open_status is None and not spec.strict_open_check),
            violated_constraints=violations,
            match_mode=match_mode,
            debug_scores=debug_scores,
        )

        if open_status is False or (open_status is None and spec.strict_open_check):
            fallback.append(candidate)
        else:
            qualified.append(candidate)

    # NEW: Two-tier sorting - tier first (ASC), then score (DESC)
    qualified.sort(key=lambda c: (c.match_tier, -c.score))
    fallback.sort(key=lambda c: (c.match_tier, -c.score))

    results: list[Candidate] = []
    if qualified:
        results.extend(qualified[:max_results])

    if len(results) < max_results and fallback:
        remaining_slots = max_results - len(results)
        results.extend(fallback[:remaining_slots])

    return results[:max_results]
