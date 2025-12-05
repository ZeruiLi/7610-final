#!/usr/bin/env python
import os
from dotenv import load_dotenv

# Load environment variables from .env
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

from config import Configuration
from services.preferences import parse_preferences

def test_gemini_parsing():
    cfg = Configuration.from_env()
    
    print(f"Configuration:")
    print(f"  LLM Provider: {cfg.llm_provider}")
    print(f"  LLM Model ID: {cfg.llm_model_id}")
    print(f"  LLM API Key: {'***' + (cfg.llm_api_key[-4:] if cfg.llm_api_key else 'None')}")
    print(f"  Local LLM (fallback): {cfg.local_llm}")
    print()
    
    # Test query
    text = "I'd like to have something make me feel warmer in Seattle downtown"
    print(f"--- Testing Query: {text} ---")
    
    try:
        spec = parse_preferences(cfg, text, history=[])
        print("SUCCESS: Parsing successful!")
        print("\nParsed Spec:")
        print(f"  City: {spec.city}")
        print(f"  Area: {spec.area}")
        print(f"  Cuisines: {spec.cuisines}")
        print(f"  Must Include: {spec.must_include_cuisines}")
        print(f"  Must Exclude: {spec.must_exclude_cuisines}")
        print(f"  Ambiance: {spec.ambiance}")
        print(f"  Distance: {spec.distance_km} km")
        
        # Verify warm food intent was understood
        warm_cuisines = ['Hotpot', 'Japanese', 'Korean', 'Sichuan']
        matched = [c for c in warm_cuisines if c in spec.cuisines or c in spec.must_include_cuisines]
        if matched:
            print(f"\nSUCCESS: Warm food intent correctly mapped to: {matched}")
        else:
            print(f"\nWARNING: Warm food intent not detected in cuisines")
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_gemini_parsing()
