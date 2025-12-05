#!/usr/bin/env python3
"""Test SSE streaming endpoint"""
import requests
import json

BASE_URL = "http://localhost:8010"

def test_stream():
    payload = {
        "query": "sichuan food in Seattle U-District for 3, budget $30 per person",
        "limit": 24,
        "session_id": None,
        "user_lat": None,
        "user_lon": None
    }
    
    print("Testing /recommend-stream...")
    print(f"Query: {payload['query']}\n")
    
    response = requests.post(
        f"{BASE_URL}/recommend-stream",
        json=payload,
        stream=True,
        headers={"Accept": "text/event-stream"}
    )
    
    if response.status_code != 200:
        print(f"Error: HTTP {response.status_code}")
        print(response.text)
        return
    
    print("Stream started. Receiving events...\n")
    
    events_received = 0
    tier_1_count = 0
    tier_2_count = 0
    
    for line in response.iter_lines():
        if not line:
            continue
        
        line_str = line.decode('utf-8')
        if line_str.startswith('data: '):
            data_json = line_str[6:]  # Remove "data: " prefix
            try:
                data = json.loads(data_json)
                
                if data.get("type") == "complete":
                    print("\n✅ Stream complete!")
                    break
                
                if data.get("type") == "error":
                    print(f"\n❌ Error: {data.get('message')}")
                    break
                
                # Regular event
                idx = data.get("index", 0)
                total = data.get("total", 0)
                tier = data.get("tier", 0)
                candidate = data.get("candidate", {})
                place = candidate.get("place", {})
                name = place.get("name", "Unknown")
                score = candidate.get("score", 0)
                is_initial = data.get("is_initial_batch", False)
                
                events_received += 1
                if tier == 1:
                    tier_1_count += 1
                else:
                    tier_2_count += 1
                
                batch_marker = "[INITIAL]" if is_initial else "[LAZY]"
                tier_marker = "✓" if tier == 1 else "⚠"
                print(f"{batch_marker} {idx+1}/{total} {tier_marker} Tier {tier}: {name} (score: {score:.2f})")
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                print(f"Raw data: {data_json}")
    
    print(f"\n=== Summary ===")
    print(f"Total events received: {events_received}")
    print(f"Tier 1 (Perfect Match): {tier_1_count}")
    print(f"Tier 2 (Relaxed Match): {tier_2_count}")
    
    if tier_1_count > 0 and tier_2_count > 0 and events_received > 0:
        print("\n✅ Test PASSED: Streaming works, both tiers present")
    elif events_received > 0:
        print("\n⚠️  Test PARTIAL: Streaming works but tier distribution may be skewed")
    else:
        print("\n❌ Test FAILED: No events received")

if __name__ == "__main__":
    test_stream()
