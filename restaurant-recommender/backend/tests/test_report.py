from models import PreferenceSpec, Candidate, Place
from services.report import build_report


def test_build_report_basic():
    spec = PreferenceSpec(city="Shanghai", distance_km=3.0)
    c = Candidate(place=Place(name="A", address="addr", lon=0, lat=0), score=0.9, reason="- ok")
    md = build_report(spec, [c], (0.0, 0.0, 1.0, 1.0))
    assert "餐厅推荐报告" in md
    assert "Top 推荐" in md
    assert "A" in md

