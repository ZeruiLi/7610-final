import asyncio
import os
import requests
from config import Configuration
from services.candidate_search import search_candidates
from models import PreferenceSpec

# Mock config
os.environ["GEOAPIFY_API_KEY"] = "cd77bb639ee24e9ea4b599ae72d19f57"
cfg = Configuration.from_env()

async def test_haidilao():
    # 1. Search specifically for Haidilao by name to see its tags
    from services.geoapify import GeoapifyClient
    client = GeoapifyClient(cfg)
    
    print("--- Searching for Haidilao Seattle ---")
    # Search around Seattle Downtown
    lat, lon = 47.6062, -122.3321
    
    # 2. Radius Search (Simulate App)
    url = "https://api.geoapify.com/v2/places"
    print("\n--- Radius Search (catering.restaurant, 1km) ---")
    params_radius = {
        "categories": "catering.restaurant",
        "filter": f"circle:{lon},{lat},1000",
        "limit": 100,
        "apiKey": cfg.geoapify_api_key
    }
    resp = requests.get(url, params=params_radius)
    data = resp.json()
    found = False
    for feature in data.get("features", []):
        props = feature["properties"]
        name = props.get("name", "")
        if "haidilao" in name.lower() or "hai di lao" in name.lower():
            print(f"FOUND IN RADIUS: {name}")
            print(f"Categories: {props.get('categories')}")
            print(f"Tags: {props.get('datasource', {}).get('raw', {}).get('tags')}") # OSM tags
            found = True
    
    if not found:
        print("NOT FOUND in Radius Search.")

    # 3. Text Search (Broader)
    queries = ["Hot Pot Seattle", "Sichuan Seattle", "Chinese Seattle"]
    for q in queries:
        print(f"\n--- Text Search: {q} ---")
        params_text = {
            "text": q,
            "bias": f"proximity:{lon},{lat}",
            "limit": 5,
            "apiKey": cfg.geoapify_api_key
        }
        resp = requests.get(url, params=params_text)
        data = resp.json()
        for feature in data.get("features", []):
            props = feature["properties"]
            print(f"Name: {props.get('name')}")
            print(f"Categories: {props.get('categories')}")
            print(f"Address: {props.get('formatted')}")
            print(f"Lat/Lon: {props.get('lat')}, {props.get('lon')}")

if __name__ == "__main__":
    asyncio.run(test_haidilao())
