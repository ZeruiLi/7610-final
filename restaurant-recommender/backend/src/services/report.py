from __future__ import annotations

from typing import List, Tuple

from models import Candidate, PreferenceSpec

KM_TO_MILES = 0.621371


def build_report(spec: PreferenceSpec, ranked: List[Candidate], bbox: Tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    radius_miles = spec.distance_km * KM_TO_MILES
    anchor_label = spec.anchor_label or "Default"
    anchor_type = (spec.anchor_type or ("area" if spec.area else "city")).lower()
    anchor_map = {
        "poi": "POI",
        "zip": "ZIP",
        "area": "Area",
        "city": "City",
        "coord": "Coord",
    }
    anchor_map_zh = {
        "poi": "兴趣点",
        "zip": "邮编",
        "area": "区域",
        "city": "城市",
        "coord": "坐标",
    }
    anchor_en = f"{anchor_map.get(anchor_type, 'City')} - {anchor_label}".strip()
    anchor_zh = f"{anchor_map_zh.get(anchor_type, '城市')}锚点 - {anchor_label}".strip()
    header = [
        "## Restaurant Recommendation Report",
        "## 餐厅推荐报告",
        "",
        f"- City / Area: {spec.city or 'Unknown'} {spec.area or ''}",
        f"- Party size: {spec.people or 'Not specified'}",
        f"- Budget per guest: {spec.budget_per_capita or 'Not specified'}",
        f"- Preferred cuisines: {', '.join(spec.cuisines) if spec.cuisines else 'Not specified'}",
        f"- Ambience: {', '.join(spec.ambiance) if spec.ambiance else 'Not specified'}",
        f"- Anchor: {anchor_en}",
        f"- 锚点: {anchor_zh}",
        f"- Search radius: {spec.distance_km:.1f} km (~{radius_miles:.1f} miles)",
        "",
        "> Note: menu items, ratings, or availability may change. Please confirm via the linked sources.",
        "",
    ]

    hard_constraints: list[str] = []
    if spec.must_include_cuisines:
        hard_constraints.append(f"Must include: {', '.join(spec.must_include_cuisines)}")
    if spec.must_exclude_cuisines:
        hard_constraints.append(f"Must exclude: {', '.join(spec.must_exclude_cuisines)}")
    if spec.dining_time:
        hard_constraints.append(f"Dining time: {spec.dining_time} (duration ≥ {spec.min_duration_min} min)" + (" [strict]" if spec.strict_open_check else " [flexible]"))

    if hard_constraints:
        header.append("### Hard Constraints")
        header.append("### 硬性条件")
        header.extend(f"- {item}" for item in hard_constraints)
        header.append("")

    lines = header
    lines.append("### Top Picks")
    lines.append("### Top 推荐")
    for idx, c in enumerate(ranked[:5], start=1):
        p = c.place
        link = f"[View map]({p.datasource_url})" if p.datasource_url else "No map link"
        source_links = ", ".join(
            f"[{src.get('title','Source')}]({src.get('url')})" if src.get("url") else src.get("title", "Source")
            for src in (c.detail_sources or [])
        ) or "No sources captured"
        highlights = (c.highlights or [])[:3]
        why = (c.why_matched or [])[:2]
        reasons: list[str] = []
        reasons.extend(highlights)
        reasons.extend(why)
        if not reasons and c.reason:
            reasons = [line.strip("- ") for line in c.reason.splitlines() if line.strip()]
        dishes = ", ".join((c.signature_dishes or [])[:4])
        if c.violated_constraints:
            reasons.append("⚠ Constraints note: " + ", ".join(c.violated_constraints))
        lines += [
            f"#### {idx}. {p.name}",
            f"- Address: {p.address or 'Not provided'}",
            f"- Score: {c.score:.3f}",
            f"- Rating: {(c.derived_rating or 0.0):.1f}/5 (source: {c.rating_source or 'unknown'})",
            f"- Match mode: {'Strict' if (c.match_mode or '').lower() != 'relaxed' else 'Relaxed'}",
            f"- Sources: {source_links} (trust {c.source_trust_score:.2f}, {c.source_hits} links)",
            f"- Distance: {c.distance_miles:.1f} miles ({c.distance_km:.1f} km)",
            f"- Map: {link}",
            f"- Hard constraints status: {'OK' if not c.violated_constraints and c.is_open_ok else 'Needs review'}",
            ("- Constraint violations: " + ", ".join(c.violated_constraints)) if c.violated_constraints else "- Constraint violations: None",
            (f"- Signature dishes: {dishes}" if dishes else "- Signature dishes: not captured"),
            ("- Highlights:\n" + "\n".join(f"  * {text}" for text in reasons) if reasons else "- Highlights: not available"),
            "",
        ]

    lines += [
        "### Search Area",
        f"- Bounding box: [{min_lon:.5f},{min_lat:.5f}] — [{max_lon:.5f},{max_lat:.5f}]",
    ]

    return "\n".join(lines)
