from models import Place, PreferenceSpec
from services.ranking import rank_candidates


def test_rank_distance_monotonic():
    spec = PreferenceSpec(city="TestCity", distance_km=5.0)
    center = (0.0, 0.0)  # lon, lat

    near = Place(name="near", address=None, lon=0.0, lat=0.01)
    far = Place(name="far", address=None, lon=0.0, lat=0.05)

    ranked = rank_candidates(spec, [near, far], bbox_center=center)
    assert ranked[0].place.name == "near"

