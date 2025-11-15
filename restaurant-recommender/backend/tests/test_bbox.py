import math

from services.bbox_builder import expand_bbox_from_center


def test_expand_bbox_basic():
    lon, lat = 121.4737, 31.2304  # Shanghai
    bbox = expand_bbox_from_center(lon, lat, 3.0)
    min_lon, min_lat, max_lon, max_lat = bbox
    assert min_lon < max_lon
    assert min_lat < max_lat
    # center must lie within bbox
    assert min_lon < lon < max_lon
    assert min_lat < lat < max_lat

