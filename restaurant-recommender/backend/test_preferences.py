import os
import asyncio
from config import Configuration
from services.preferences import parse_preferences

# Mock config
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["LOCAL_LLM"] = "llama3.2"
cfg = Configuration.from_env()

def test_parsing():
    text = "I'd like to have something make me feel warmer in Seattle downtown"
    print(f"--- Testing Query: {text} ---")
    try:
        spec = parse_preferences(cfg, text, history=[])
        print("Parsed Spec:")
        print(spec)
        print(f"Cuisines: {spec.cuisines}")
        print(f"Must Include: {spec.must_include_cuisines}")
        print(f"Ambiance: {spec.ambiance}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_parsing()
