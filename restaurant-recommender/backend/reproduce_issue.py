import asyncio
import os
from src.config import Configuration
from src.services.preferences import parse_preferences
from src.services.candidate_search import search_candidates
from src.services.ranking import rank_candidates
from src.services.details import fetch_details_async
from src.models import Place

async def main():
    # Force load env vars
    from dotenv import load_dotenv
    load_dotenv(".env")
    
    cfg = Configuration.from_env()
    query = "spicy food in Seattle near UW"
    
    print(f"--- parsing '{query}' ---")
    spec = parse_preferences(cfg, query)
    print(f"Spec: city={spec.city}, area={spec.area}, cuisines={spec.cuisines}, must_include={spec.must_include_cuisines}")
    
    print("\n--- searching candidates ---")
    places, bbox = search_candidates(cfg, spec, min_results=10)
    print(f"Found {len(places)} places")
    for p in places[:5]:
        print(f"  - {p.name} ({p.tags})")
        
    print("\n--- ranking ---")
    center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
    ranked = rank_candidates(spec, places, bbox_center=center)
    print(f"Ranked {len(ranked)} candidates")
    
    print("\n--- fetching details for top 5 ---")
    top_5 = ranked[:5]
    for c in top_5:
        ctx = await fetch_details_async(c.place)
        print(f"Candidate: {c.place.name}")
        print(f"  Sources: {len(ctx.sources)}")
        print(f"  Trust Score: {ctx.trust_score}")
        print(f"  Extracted Ratings: {ctx.extracted.get('ratings')}")
        print(f"  First Source: {ctx.sources[0]['title'] if ctx.sources else 'None'}")

if __name__ == "__main__":
    asyncio.run(main())
