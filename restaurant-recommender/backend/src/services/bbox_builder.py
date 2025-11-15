from __future__ import annotations

import math
from typing import Tuple


def expand_bbox_from_center(lon: float, lat: float, km: float) -> Tuple[float, float, float, float]:
    """Create a rectangular bbox around (lon,lat) by ±km in both axes.

    Returns (min_lon, min_lat, max_lon, max_lat)
    """
    # degrees per km
    dlat = km / 110.574
    dlon = km / (111.320 * math.cos(math.radians(lat)) if math.cos(math.radians(lat)) != 0 else 1e-6)
    min_lon = lon - dlon
    max_lon = lon + dlon
    min_lat = lat - dlat
    max_lat = lat + dlat
    return (min_lon, min_lat, max_lon, max_lat)

