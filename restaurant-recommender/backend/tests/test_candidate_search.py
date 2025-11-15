from __future__ import annotations

from services.candidate_search import _lookup_us_location, _normalize_city, _normalize_token


def test_normalize_city_strips_state_abbrev() -> None:
    assert _normalize_city("Seattle, WA") == "seattle"
    assert _normalize_city("Los Angeles CA") == "los angeles"


def test_lookup_returns_area_coordinates_when_available() -> None:
    coords = _lookup_us_location("Seattle", "Capitol Hill")
    assert coords is not None
    lon, lat = coords
    assert -122.33 < lon < -122.30
    assert 47.60 < lat < 47.65


def test_lookup_falls_back_to_city_center() -> None:
    coords = _lookup_us_location("Seattle", "Nonexistent Neighborhood")
    assert coords is not None
    lon, lat = coords
    assert -123 < lon < -122
    assert 47 < lat < 48


def test_lookup_supports_aliases() -> None:
    coords = _lookup_us_location("NYC", "Flushing")
    assert coords is not None
    lon, lat = coords
    assert -74 < lon < -73
    assert 40 < lat < 41
