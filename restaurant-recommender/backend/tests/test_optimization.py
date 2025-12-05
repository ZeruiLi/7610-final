import unittest
from unittest.mock import MagicMock, patch
from models import Place, PreferenceSpec
from services.details import _source_weight, fetch_details, DetailContext
from services.reasoner import build_reason
from config import Configuration

class TestOptimization(unittest.TestCase):
    def test_source_weight(self):
        p = Place(name="Test Place", address="123 Main St", lon=0, lat=0)
        
        # High authority
        self.assertEqual(_source_weight("https://www.theinfatuation.com/reviews/test", p), 1.2)
        self.assertEqual(_source_weight("https://www.eater.com/maps/best-test", p), 1.2)
        
        # Standard
        self.assertEqual(_source_weight("https://www.yelp.com/biz/test", p), 1.0)
        
        # Low quality / Aggregator
        self.assertEqual(_source_weight("https://www.yellowpages.com/test", p), 0.0)
        self.assertEqual(_source_weight("https://restaurantji.com/test", p), 0.0)

    @patch("services.details._SEARCH")
    def test_fetch_details_query_and_truncation(self, mock_search):
        p = Place(name="Sushi Zen", address="123 Pike St, Seattle, WA 98101", lon=0, lat=0)
        
        # Mock search response with mixed quality sources
        mock_search.run.return_value = {
            "results": [
                {"title": "Bad Site", "url": "https://yellowpages.com/bad", "snippet": "Bad content " * 100},
                {"title": "Good Site", "url": "https://www.theinfatuation.com/good", "snippet": "Good content " * 10},
                {"title": "Okay Site", "url": "https://www.google.com/maps/place", "snippet": "Okay content " * 10},
            ]
        }
        
        ctx = fetch_details(p)
        
        # Verify query format
        args, kwargs = mock_search.run.call_args
        query = args[0]["input"]
        self.assertIn("Sushi Zen", query)
        self.assertIn("Seattle, WA 98101", query)
        self.assertIn("restaurant reviews menu", query)
        
        # Verify source filtering and sorting
        # Bad site should be filtered out (weight 0.0)
        self.assertEqual(len(ctx.sources), 2)
        self.assertEqual(ctx.sources[0]["title"], "Good Site") # Highest weight first
        self.assertEqual(ctx.sources[1]["title"], "Okay Site")
        
        # Verify text content starts with high weight source
        self.assertTrue(ctx.raw_text.startswith("Source: Good Site"))

    def test_reasoner_fallback(self):
        cfg = Configuration()
        cfg.llm_provider = None # Force rule-based fallback
        cfg.local_llm = None
        
        p = Place(name="Test Place", address="123 Main St", lon=0, lat=0, tags=["catering.restaurant", "catering.sichuan"], rating=4.5)
        spec = PreferenceSpec(city="Seattle")
        
        # Empty details
        detail = DetailContext(sources=[], raw_text="", extracted={}, trust_score=0.0, hits=0)
        
        reason = build_reason(cfg, spec, p, detail)
        
        # Check fallback highlights
        highlights = reason["highlights"]
        self.assertTrue(any("Specializes in: Sichuan" in h for h in highlights))
        self.assertTrue(any("Overall rating: 4.5/5.0" in h for h in highlights))
        self.assertTrue(any("Could not find trusted reviews" in r for r in reason["risks"]))

if __name__ == "__main__":
    unittest.main()
