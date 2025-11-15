"""Data models for restaurant recommender MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class GeocodeResult:
    lon: float
    lat: float
    bbox: Optional[tuple[float, float, float, float]] = None  # min_lon, min_lat, max_lon, max_lat


@dataclass
class Place:
    name: str
    address: Optional[str]
    lon: float
    lat: float
    website: Optional[str] = None
    opening_hours: Optional[str] = None
    datasource_url: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    rating: Optional[float] = None


@dataclass
class PreferenceSpec:
    city: str
    area: Optional[str] = None
    datetime: Optional[str] = None
    people: Optional[int] = None
    budget_per_capita: Optional[float] = None
    cuisines: list[str] = field(default_factory=list)
    taboos: list[str] = field(default_factory=list)
    ambiance: list[str] = field(default_factory=list)
    need_private_room: Optional[bool] = None
    rating_min: Optional[float] = None
    distance_km: float = 3.0
    lang: str = "en"
    must_include_cuisines: list[str] = field(default_factory=list)
    must_exclude_cuisines: list[str] = field(default_factory=list)
    dining_time: Optional[str] = None  # ISO8601 or weekday/time text
    min_duration_min: int = 60
    strict_open_check: bool = True
    anchor_poi: Optional[str] = None
    anchor_zip: Optional[str] = None
    anchor_type: Optional[str] = None
    anchor_label: Optional[str] = None


@dataclass
class Candidate:
    place: Place
    score: float
    reason: str
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    # v2 enriched fields
    highlights: list[str] = field(default_factory=list)
    signature_dishes: list[str] = field(default_factory=list)
    why_matched: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    detail_sources: list[dict] = field(default_factory=list)  # {title,url}
    match_cuisine: bool = False
    match_ambience: bool = False
    match_budget: bool = False
    match_distance: bool = False
    match_popularity: bool = False
    primary_tags: list[str] = field(default_factory=list)
    reliability_score: float = 0.0
    distance_km: float = 0.0
    distance_miles: float = 0.0
    source_hits: int = 0
    source_trust_score: float = 0.0
    is_open_ok: bool = True
    violated_constraints: list[str] = field(default_factory=list)
