import asyncio
from dotenv import load_dotenv
load_dotenv("backend/.env")

from config import Configuration
from services.preferences import parse_preferences
from services.candidate_search import search_candidates
from services.ranking import rank_candidates

async def main():
    cfg = Configuration.from_env()
    
    # 用户期望的测试查询
    query = "sichuan food in Seattle U-District for 3, budget $30 per person, tonight at 7pm"
    
    print(f"=== Testing Query ===")
    print(f"Query: {query}")
    print()
    
    # 解析偏好
    spec = parse_preferences(cfg, query)
    print(f"=== Parsed Preferences ===")
    print(f"City: {spec.city}")
    print(f"Area: {spec.area}")
    print(f"Cuisines: {spec.cuisines}")
    print(f"Must Include: {spec.must_include_cuisines}")
    print(f"People: {spec.people}")
    print(f"Budget: ${spec.budget_per_capita}")
    print(f"Dining Time: {spec.dining_time}")
    print()
    
    # 搜索候选（期望24个）
    print(f"=== Searching Candidates (min_results=24) ===")
    places, bbox = search_candidates(cfg, spec, min_results=24)
    print(f"Found: {len(places)} places")
    print()
    
    # 展示前10个
    print(f"=== Top 10 Candidates ===")
    for i, p in enumerate(places[:10], 1):
        cuisine_tags = [t for t in p.tags if 'restaurant' in t]
        print(f"{i}. {p.name}")
        print(f"   Tags: {cuisine_tags}")
        print(f"   Rating: {p.rating}")
        print()
    
    # 排序（期望返回24个排序后的结果）
    center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
    ranked = rank_candidates(spec, places, bbox_center=center, max_results=24)
    
    print(f"=== Ranking Results ===")
    print(f"Total ranked: {len(ranked)} candidates")
    print()
    
    # 展示前8个（前端显示的数量）
    print(f"=== Top 8 for Frontend Display ===")
    for i, c in enumerate(ranked[:8], 1):
        violations = getattr(c.place, "_violations", [])
        print(f"{i}. {c.place.name} (Score: {c.score:.2f}, Tier: {c.match_tier})")
        print(f"   Match: cuisine={c.match_cuisine}, distance={c.match_distance}")
        if violations:
            print(f"   Violations: {violations}")
        print()
    
    print(f"=== Summary ===")
    print(f"✓ Candidates found: {len(places)}/24")
    print(f"✓ Ranked results: {len(ranked)}/24")
    print(f"✓ Frontend display: 8 (with 'Load More' for remaining {len(ranked)-8})")

if __name__ == "__main__":
    asyncio.run(main())
